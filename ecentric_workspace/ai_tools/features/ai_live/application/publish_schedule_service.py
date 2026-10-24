# Copyright (c) 2026, eCentric and contributors
"""fix10g: phat hanh ban nhap lich live -> so phien ban moi; app tren cac may nhan o lan tai get_config ke tiep
(hoac ngay neu may hieu lenh refresh_config).

Truoc khi ghi: kiem ca bo (trung gio trong phien, may + brand, cong OBS, suc chua may tinh ca lan dang giu gio cu).
Khi ghi: lan dang live / sap len song (trong lock_min phut) cua ban cu duoc GIU toi het lan do (tru khi khan,
hoac chi keo dai gio ket thuc) - xem domain/schedule_rules. App sua lich (push_slots) di cung duong ghi nay,
nguon "app", khong giu gio (app da tu ap)."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class PublishScheduleService:
    def __init__(self, sessions=None, machines=None, schedule=None, commands=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.schedule = schedule or DS.schedule()
        self.commands = commands or DS.commands()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, names=None, urgent=None, note=""):
        """names: ma phien can phat hanh (rong = moi ban nhap); urgent: ma phien ap ngay du sap len song."""
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        names, urgent = _common.id_list(names), set(_common.id_list(urgent))
        all_s = self.sessions.list()
        targets = [s for s in all_s if s.get("draft") and (not names or s["id"] in names)]
        if not targets:
            raise C.AiLiveError(C.PubMsg.NO_DRAFT)
        stale = next((s for s in targets if P.draft_state(s) == C.DraftState.STALE), None)
        if stale:
            raise C.AiLiveError(C.PubMsg.STALE % (stale["title"], stale["published_version"]))
        afters = {s["id"]: P.draft_view(s) for s in targets}
        holds, errors = self.plan(all_s, afters, urgent)
        if errors:
            return {"published": False, "errors": errors}
        src = C.PubSource.URGENT if urgent & set(afters) else C.PubSource.ERP
        return dict(self.write(user, all_s, afters, holds, src, str(note or "")[:280]), published=True)

    def plan(self, all_s, afters, urgent=(), no_hold=False):
        """-> (holds {id: (until, why)}, errors [{id, title, error}]) cho bo `afters` {id: view} thay ban phat hanh."""
        now, lock_s = self.clock(), self.schedule.settings()["lock_min"] * 60
        machines = {m["machine_code"]: m for m in self.machines.sync_states()}
        by_id = {s["id"]: s for s in all_s}
        views, extra, holds, errs = {}, {}, {}, []
        for s in all_s:
            sid = s["id"]
            views[sid] = dict(afters.get(sid) or P.published_view(s), enabled=s["enabled"])
            if sid in afters:
                until, why = (0, "") if no_hold else P.hold_for_publish(P.published_view(s), afters[sid], now, lock_s,
                                                                         sid in urgent)
                prev = P.published_view(s)
            else:
                until, why, prev = s.get("held_until_ts") or 0, s.get("held_why") or "", s.get("prev")
            if until and until > now and prev:
                holds[sid] = (until, why)
                extra[sid] = (prev["machine"], P.held_slot(prev, until))
        today = datetime.fromtimestamp(now, R._VN).date()
        for sid, v in afters.items():
            errs += [([sid], e) for e in self._own(by_id[sid], v, machines, today)]
        errs += P.port_errors(views) + P.capacity_errors(views, machines, today, extra)
        out = []
        for ids, msg in errs:
            hit = next((i for i in ids if i in afters), None)
            if hit and not any(e["error"] == msg for e in out):
                out.append({"id": hit, "title": by_id[hit]["title"], "error": msg})
        return {k: v for k, v in holds.items() if k in afters}, out

    @staticmethod
    def _own(sess, v, machines, today):
        clash = S.self_overlap(v["slots"], today)
        if clash:
            yield C.SessMsg.SLOT_OVERLAP % (clash[1], clash[0])
        if v["machine"]:
            m = machines.get(v["machine"])
            if not m:
                yield C.SessMsg.NO_MACHINE
            elif sess["brand"] and sess["brand"] not in _common.machine_brands(m):
                yield C.SessMsg.BRAND_OFF % (sess["brand"], v["machine"])

    def write(self, user, all_s, afters, holds, source, note="", refresh=True):
        """Ghi ban phat hanh moi cho cac phien trong `afters`; tra {version, changes, holds, refresh_sent}."""
        now = self.clock()
        version = self.schedule.next_version(user, now)
        by_id = {s["id"]: s for s in all_s}
        changes, touched = [], {}
        for sid, after in afters.items():
            s, before = by_id[sid], P.published_view(by_id[sid])
            until, why = holds.get(sid, (0, ""))
            prev = dict(before, version=int(s.get("published_version") or 0))   # ban cu kem so ban (get_config luc giu gio)
            self.sessions.publish(sid, after, {"version": version, "ts": now, "source": source, "prev": prev,
                                               "held_until": until, "held_why": why,
                                               "keep_draft": source == C.PubSource.APP})   # nhap cua nguoi khac -> lech
            changes.append({"session": sid, "title": s["title"], "brand": s["brand"], "texts": P.diff_texts(before, after),
                            "held_until": until, "held_why": why, "before": before, "after": after})
            for code in {before["machine"], after["machine"]} - {""}:
                touched.setdefault(code, sid)
        self.schedule.insert_version({"version": version, "source": source, "published_by": user, "published_ts": now,
                                      "note": note, "sessions": list(afters), "machines": sorted(touched), "changes": changes})
        sent = []
        if refresh and self.schedule.settings()["refresh_on_publish"]:
            for code, sid in sorted(touched.items()):
                self.commands.insert({"live": sid, "machine": code, "action": C.CMD_REFRESH, "args": {"version": version},
                                      "created_ts": now, "requested_by": user})
                sent.append(code)
        return {"version": version, "changes": [{k: c[k] for k in ("session", "title", "texts", "held_until", "held_why")}
                                                for c in changes], "refresh_sent": sent}
