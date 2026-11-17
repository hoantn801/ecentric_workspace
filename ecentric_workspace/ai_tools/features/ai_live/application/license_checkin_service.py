# Copyright (c) 2026, eCentric and contributors
"""license_checkin (app bao ve luc mo app khi can + moi 6 gio, KHONG dang nhap).
CHI tra blocked khi Hoan da bam Khoa (blocked_manual) va log_only tat - luon kem manual: true.
May ERP chua tung biet (key tay truoc 17/11) -> tao ban ghi approved (via_checkin=1), tra ok. Loi bat ky -> ok.
via_checkin: ban ghi chi dua tren du lieu may TU KHAI (checkin khong gui license de ERP kiem) -> license_request
cua may nay KHONG tu cap ma cho Hoan duyet (neu khong, ai doc ec_online.py cung tu "bao ve" roi xin duoc license).
Da duyet tren trang -> via_checkin = 0."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import ec_license_issuer as I
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R

OK = {"status": L.Reply.OK}


class LicenseCheckinService:
    def __init__(self, settings=None, machines=None, dists=None, events=None, locks=None, notifier=None, clock=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events, self.locks = dists or D.dists(), events or D.events(), locks or D.locks()
        self.notifier, self.clock = notifier or D.notifier(), clock or D.clock()

    def execute(self, raw, ip):
        st = self.settings.get()
        if st["killed"] or not st["enabled"]:
            return dict(OK)
        try:
            p = R.clean_payload(raw)
        except L.BadPayload:
            return dict(OK)
        keys = [D.guid_key(p["fp"]["guid_h"])]
        if not self.locks.lock(keys):
            return dict(OK)
        notes = []
        try:
            m = self._record(p, ip, notes)
            self.locks.commit()
        except Exception:
            self.locks.rollback()
            raise
        finally:
            self.locks.unlock(keys)
        for kind, name in notes:
            self.notifier.enqueue(kind, name)
        if m and m.get("status") == L.Status.BLOCKED and m.get("blocked_manual") and not st["log_only"]:
            return {"status": L.Reply.BLOCKED, "manual": True, "message": m.get("block_message") or L.Msg.DEFAULT_BLOCK}
        return dict(OK)

    def _record(self, p, ip, notes):
        now, product = self.clock(), p["product"]
        m = I.match_machine(self.machines.by_guid(p["fp"]["guid_h"]), p["fp"])
        row = D.install_seen(p, now, ip)
        if p.get("license_hw"):
            row["license_hw"] = p["license_hw"]
        if m is None:
            dist = I.verify_dist(p["dist"], self.settings.dist_secret())
            did = self.dists.ensure(dist) if dist else None
            vals = dict(D.seen_vals(p, ip, now), fp=p["fp"], status=L.Status.APPROVED, reason=L.REASON_MANUAL_KEY,
                        via_checkin=1, source_dist=did, first_ip=ip, first_seen=now, approved_by="auto", approved_at=now)
            name = self.machines.create(vals, [dict(row, product=product, hw=p["hw"])])
            if did:
                self.dists.set_first(did, name, now)
            self.events.add(name, product, L.Kind.CHECKIN, ip, "Guest", "máy chưa có trên ERP – ghi nhận (%s)"
                            % L.REASON_MANUAL_KEY)
            return None
        inst, clone = D.install_of(m, product), D.check_clone(m, p)
        if not (inst or {}).get("hw"):
            row["hw"] = p["hw"]
        keep = clone or bool(m.get("clone_warning"))
        seen = D.seen_vals(p, ip, now, clone=keep)
        if not keep:
            seen["fp"] = R.merge_fp(m["fp"], p["fp"])
        self.machines.touch(m["name"], seen)
        self.machines.upsert_install(m["name"], product, row)
        self.events.add(m["name"], product, L.Kind.CHECKIN, ip, "Guest", p["build_id"])
        if clone:
            self.machines.save(m["name"], {"clone_warning": 1, "clone_host": p["host"][:80], "notified_clone": 1})
            self.events.add(m["name"], product, L.Kind.CLONE, ip, "Guest", "tên máy mới: %s" % p["host"])
            notes.append(("clone", m["name"]))
        return m
