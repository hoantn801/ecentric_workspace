# Copyright (c) 2026, eCentric and contributors
"""license_request (app xin license, KHONG dang nhap): giai ma yeu cau -> kiem chu ky ma goi -> khoa dong ->
nhan ra may -> decide() (luat Hoan chot 17/11, khong sua) -> cap / cho duyet / khoa.
Song con: loi bat ky -> pending / unknown, KHONG BAO GIO blocked do loi xu ly. Khong ghi token vao dau ca.
Tin nhan cho may khach khong lo ly do / ten may nguon / ten goi (QC T8)."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import ec_license_issuer as I
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R


class NotReady(Exception):
    """Thieu / hong khoa ky tren ERP -> tra unknown (app hien o dan key tay)."""


class LicenseRequestService:
    def __init__(self, settings=None, machines=None, dists=None, events=None, locks=None, notifier=None, clock=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events, self.locks = dists or D.dists(), events or D.events(), locks or D.locks()
        self.notifier, self.clock = notifier or D.notifier(), clock or D.clock()

    def execute(self, raw, ip):
        st = self.settings.get()
        if st["killed"] or not st["enabled"]:
            return {"status": L.Reply.UNKNOWN, "message": ""}
        try:
            p = R.clean_payload(raw)
        except L.BadPayload:
            return _pending()
        try:
            ident = I.decode_request(p["product"], p)
        except I.RequestError as e:
            self.events.add(None, p["product"], L.Kind.BLOCKED, ip, "Guest", "%s · %s" % (e, p["host"]))
            return {"status": L.Reply.BLOCKED, "message": L.Msg.BAD_CODE}
        dist = I.verify_dist(p["dist"], self.settings.dist_secret())
        keys = [D.guid_key(p["fp"]["guid_h"])] + (["d:" + dist["dist_id"]] if dist else [])
        if not self.locks.lock(keys):
            return _pending()
        notes, out, err = [], None, ""
        try:
            out = self._decide(p, ident, dist, ip, st, notes)
            self.locks.commit()
        except NotReady as e:
            self.locks.rollback()
            err = str(e)
        except Exception:
            self.locks.rollback()
            raise
        finally:
            self.locks.unlock(keys)
        if out is None:   # khoa ky tren ERP thieu / hong: ghi nhat ky (khong co noi dung khoa), app hien o dan key tay
            self.events.add(None, p["product"], L.Kind.ERROR, ip, "Guest",
                            "Thiếu / sai khoá ký %s trong EC License Settings (%s)" % (L.PRODUCT_LABEL[p["product"]], err))
            self.locks.commit()
            return {"status": L.Reply.UNKNOWN, "message": L.Msg.NOT_READY}
        for kind, name in notes:   # sau commit: may moi cho duyet / nghi nhan ban -> Teams 1 lan
            self.notifier.enqueue(kind, name)
        return out

    def _decide(self, p, ident, dist, ip, st, notes):
        now, product = self.clock(), p["product"]
        m = I.match_machine(self.machines.by_guid(p["fp"]["guid_h"]), p["fp"])
        owner, count, did = None, 0, None
        if dist:
            did = self.dists.ensure(dist)
            owner = self.machines.dist_owner(did, exclude=m and m["name"])
            count = self.machines.count_approved(did)
        fed = m
        if m and m.get("via_checkin") and m.get("status") == L.Status.APPROVED:
            fed = dict(m, status=L.Status.PENDING)   # ban ghi tu bao ve = may TU KHAI -> khong tu cap (A.4.1 buoc 6)
        decision, reason = I.decide(fed, dist, owner, ip, R.office_ips(st["office_ips"]), product=product,
                                    hw=ident["hw"], fp=p["fp"], now=now, dist_count=count)
        if fed is not m and decision == "pending":
            reason = L.REASON_MANUAL_ASK
        if decision == "issue":
            try:
                token = I.issue(product, R.parse_secret(self.settings.secret(product)), ident,
                                cust=(m or {}).get("label") or p["host"] or "eCentric")
            except Exception as e:   # khoa thieu / sai dinh dang: KHONG lo noi dung khoa
                raise NotReady(type(e).__name__)
            name = self._issued(m, p, ident, did, ip, now, reason, notes)
            self.events.add(name, product, L.Kind.ISSUED, ip, "Guest", reason)
            return {"status": L.Reply.ISSUED, "token": token}
        if decision == "blocked":
            self.machines.touch(m["name"], D.seen_vals(p, ip, now, clone=True))
            return {"status": L.Reply.BLOCKED, "message": m.get("block_message") or L.Msg.DEFAULT_BLOCK}
        self._pending_machine(m, p, ident, did, owner, ip, now, reason, notes)
        return _pending()

    def _issued(self, m, p, ident, did, ip, now, reason, notes):
        product, inst = p["product"], D.install_of(m, p["product"])
        row = dict(D.install_seen(p, now, ip), hw=ident["hw"], license_hw=ident["hw"], license_issued_at=now,
                   pending_hw="")
        if ident.get("mid"):
            row["machine_id"] = ident["mid"]
        if m is None:
            vals = dict(D.seen_vals(p, ip, now), fp=p["fp"], status=L.Status.APPROVED, reason=reason[:140],
                        source_dist=did, first_ip=ip, first_seen=now, approved_by="auto", approved_at=now)
            name = self.machines.create(vals, [dict(row, product=product)])
        else:
            name, clone = m["name"], D.check_clone(m, p)
            if inst and inst.get("hw") and inst["hw"] != ident["hw"]:
                row["reissued_at"] = now          # QC C1: tu cap lai 1 lan / 30 ngay / app
            keep = clone or bool(m.get("clone_warning"))
            seen = D.seen_vals(p, ip, now, clone=keep)
            if not keep:
                seen["fp"] = R.merge_fp(m["fp"], p["fp"])
            self.machines.touch(name, seen)
            self.machines.upsert_install(name, product, row)
            if clone:
                self._flag_clone(m, p, ip, notes)
        if did:
            self.dists.set_first(did, name, now)
            self.dists.set_count(did, self.machines.count_approved(did))
        return name

    def _pending_machine(self, m, p, ident, did, owner, ip, now, reason, notes):
        product, row = p["product"], dict(D.install_seen(p, now, ip), pending_hw=ident["hw"])
        if ident.get("mid"):
            row["machine_id"] = ident["mid"]
        if m is None:
            vals = dict(D.seen_vals(p, ip, now), fp=p["fp"], status=L.Status.PENDING, reason=reason[:140],
                        source_dist=did, parent_machine=(owner or {}).get("name"), first_ip=ip, first_seen=now,
                        notified_pending=1)
            name = self.machines.create(vals, [dict(row, product=product)])
            self.events.add(name, product, L.Kind.PENDING, ip, "Guest", reason)
            notes.append(("pending", name))
            return
        name = m["name"]
        self.machines.touch(name, D.seen_vals(p, ip, now, clone=m.get("clone_warning")))
        self.machines.upsert_install(name, product, row)
        if m.get("status") == L.Status.APPROVED:   # may da duyet xin cho ma phan cung khac (C1) -> cho Hoan duyet lai
            self.machines.save(name, {"status": L.Status.PENDING, "reason": reason[:140], "notified_pending": 1})
            self.events.add(name, product, L.Kind.PENDING, ip, "Guest", reason)
            notes.append(("pending", name))

    def _flag_clone(self, m, p, ip, notes):
        self.machines.save(m["name"], {"clone_warning": 1, "clone_host": p["host"][:80], "notified_clone": 1})
        self.events.add(m["name"], p["product"], L.Kind.CLONE, ip, "Guest", "tên máy mới: %s" % p["host"])
        notes.append(("clone", m["name"]))


def _pending():
    return {"status": L.Reply.PENDING, "message": I.CLIENT_PENDING_MSG, "poll_s": L.POLL_S}
