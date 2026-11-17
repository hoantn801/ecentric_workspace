# Copyright (c) 2026, eCentric and contributors
"""Trang Ban quyen - ghi: Duyet (nhieu may), Khoa / Bo khoa (tung may), dat ten / ghi chu, nhan goi, cong tac.
Moi thay doi ghi EC License Event (ai, luc nao, truoc -> sau). Doi trang thai may giu CUNG khoa dong voi
license_request (nut Duyet va app dang xin khong giam len nhau). Khoa chi co hieu luc o LAN MO APP SAU."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R

_ST = {L.Status.PENDING: "Chờ duyệt", L.Status.APPROVED: "Đang dùng", L.Status.BLOCKED: "Bị khoá"}


class LicenseActionService:
    def __init__(self, settings=None, machines=None, dists=None, events=None, locks=None, clock=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events, self.locks = dists or D.dists(), events or D.events(), locks or D.locks()
        self.clock = clock or D.clock()

    # ------------------------------------------------------------ trang thai may
    def approve(self, user, roles, names):
        D.require_admin(roles)
        names = [str(n)[:20] for n in (names or []) if str(n).strip()]
        if not names:
            raise L.LicenseError(L.Msg.NEED_PICK)
        if len(names) > L.MAX_APPROVE:
            raise L.LicenseError(L.Msg.TOO_MANY % L.MAX_APPROVE)
        done, skipped = [], []
        for name in dict.fromkeys(names):
            try:
                self._locked(name, lambda m: self._approve(user, m))
                done.append(name)
            except L.LicenseError as e:
                skipped.append({"name": name, "why": str(e)})
        return {"approved": done, "skipped": skipped, "message": L.Msg.APPROVED if done else ""}

    def block(self, user, roles, name, message):
        D.require_admin(roles)
        msg = R.clean_text(message, L.MAX_BLOCK_MSG) or L.Msg.DEFAULT_BLOCK
        self._locked(name, lambda m: self._block(user, m, msg))
        return {"name": name, "log_only": self.settings.get()["log_only"]}

    def unblock(self, user, roles, name):
        D.require_admin(roles)
        self._locked(name, lambda m: self._unblock(user, m))
        return {"name": name}

    def _approve(self, user, m):
        if m["status"] != L.Status.PENDING:
            raise L.LicenseError(L.Msg.NOT_PENDING % m["name"])
        self._set_approved(user, m)
        self.events.add(m["name"], "", L.Kind.APPROVE, "", user, "trạng thái: Chờ duyệt → Đang dùng")

    def _block(self, user, m, msg):
        if m["status"] == L.Status.BLOCKED and m.get("blocked_manual"):
            raise L.LicenseError(L.Msg.ALREADY_BLOCKED % m["name"])
        self.machines.save(m["name"], {"status": L.Status.BLOCKED, "blocked_manual": 1, "block_message": msg})
        self.events.add(m["name"], "", L.Kind.BLOCK, "", user, "trạng thái: %s → Bị khoá · lời nhắn: %s"
                        % (_ST.get(m["status"], m["status"]), msg))

    def _unblock(self, user, m):
        if m["status"] != L.Status.BLOCKED:
            raise L.LicenseError(L.Msg.NOT_BLOCKED % m["name"])
        self._set_approved(user, m, unblock=True)
        self.events.add(m["name"], "", L.Kind.UNBLOCK, "", user, "trạng thái: Bị khoá → Đang dùng")

    def _set_approved(self, user, m, unblock=False):
        now = self.clock()
        vals = {"status": L.Status.APPROVED, "notified_pending": 0, "via_checkin": 0}
        if unblock:
            vals.update(blocked_manual=0)
        if not m.get("approved_at") or m["status"] == L.Status.PENDING:
            vals.update(approved_by=user, approved_at=now)
        self.machines.save(m["name"], vals)
        for i in m.get("installs") or []:      # ma phan cung dang cho -> thanh ma da duyet (lan xin sau duoc cap)
            if i.get("pending_hw"):
                row = {"hw": i["pending_hw"], "pending_hw": ""}
                if i.get("hw") and i["hw"] != i["pending_hw"]:
                    row["reissued_at"] = now
                self.machines.upsert_install(m["name"], i["product"], row)
        did = m.get("source_dist")
        if did:
            self.dists.set_first(did, m["name"], now)
            self.dists.set_count(did, self.machines.count_approved(did))

    def _locked(self, name, fn):
        m = self.machines.get(str(name or "")[:20])
        if not m:
            raise L.LicenseError(L.Msg.NOT_FOUND % name)
        keys = [D.guid_key(m["fp"]["guid_h"])] if m["fp"].get("guid_h") else ["m:" + m["name"]]
        if not self.locks.lock(keys):
            raise L.LicenseError(L.Msg.BUSY % m["name"])
        try:
            fn(self.machines.get(m["name"]))      # doc lai TRONG khoa: app co the vua doi may nay
            self.locks.commit()
        except Exception:
            self.locks.rollback()
            raise
        finally:
            self.locks.unlock(keys)

    # ------------------------------------------------------------ ten / ghi chu / goi / cong tac
    def update_machine(self, user, roles, name, label=None, note=None):
        D.require_admin(roles)
        m = self.machines.get(str(name or "")[:20])
        if not m:
            raise L.LicenseError(L.Msg.NOT_FOUND % name)
        vals, diff = {}, []
        for k, v, n in (("label", label, L.MAX_LABEL), ("note", note, L.MAX_NOTE)):
            if v is None:
                continue
            v = R.clean_text(v, n) if k == "label" else str(v).replace("\x00", "").strip()[:n]
            if v != (m.get(k) or ""):
                vals[k] = v
                diff.append("%s: %s → %s" % ("tên" if k == "label" else "ghi chú", m.get(k) or "(trống)", v or "(trống)"))
        if vals:
            self.machines.save(m["name"], vals)
            self.events.add(m["name"], "", L.Kind.EDIT, "", user, " · ".join(diff)[:1000])
        return {"name": m["name"], "changed": bool(vals)}

    def update_dist(self, user, roles, dist_id, label):
        D.require_admin(roles)
        d = self.dists.get(str(dist_id or "")[:64])
        if not d:
            raise L.LicenseError(L.Msg.DIST_NOT_FOUND % dist_id)
        label, old = R.clean_text(label, L.MAX_LABEL), d.get("label") or ""
        if label != old:
            self.dists.set_label(d["name"], label)
            self.events.add(None, "", L.Kind.DIST_EDIT, "", user, "gói %s: nhãn %s → %s"
                            % (d["name"][:8], old or "(trống)", label or "(trống)"))
        return {"name": d["name"], "label": label}

    def set_mode(self, user, roles, enabled, log_only):
        D.require_admin(roles)
        st = self.settings.get()
        en, lo = int(bool(enabled)), int(bool(log_only))
        if (en, lo) != (st["enabled"], st["log_only"]):
            self.settings.set_mode(en, lo)
            self.events.add(None, "", L.Kind.MODE, "", user, "Bật API: %s → %s · Chỉ ghi nhận: %s → %s"
                            % (_onoff(st["enabled"]), _onoff(en), _onoff(st["log_only"]), _onoff(lo)))
        return {"enabled": en, "log_only": lo}


def _onoff(v):
    return "bật" if v else "tắt"
