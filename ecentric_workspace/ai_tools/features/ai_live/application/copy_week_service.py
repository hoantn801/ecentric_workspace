# Copyright (c) 2026, eCentric and contributors
"""18/11 (hop dong lich live muc 7): chep tuan CO XEM TRUOC xung dot. Chep cac khung "chi ngay" (ke ca khung dang tat,
giu nguyen trang thai) cua tuan `week` sang tuan sau, vao BAN NHAP tung phien (app nhan khi Phat hanh). Khung lap hang
tuan khong chep (tu co o tuan sau). Xem truoc cho biet: moi phien them khung nao, bo qua khung nao vi da co y het,
phien nao loi (trung gio trong phien -> khong chep phien do), may nao se vuot so live cung luc o tuan dich (do - phat
hanh se bi chan toi khi sua). apply = luu; loi o 1 phien khong chan phien khac."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.week_schedule_service import first_ts, week_start
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class CopyWeekService:
    def __init__(self, sessions=None, machines=None, clock=None, draft=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts
        self.draft = draft or SaveDraftService(self.sessions, self.machines, self.clock)

    def execute(self, user, roles, week=None, apply=False):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        src = week_start(week, self.clock())
        dst = src + timedelta(days=7)
        lo, hi = src.isoformat(), (src + timedelta(days=6)).isoformat()
        sessions = self.sessions.list()
        items, new_slots = [], {}
        for s in sessions:
            v = P.draft_view(s)
            item = self._plan(s, v["slots"], lo, hi)
            if item is None:
                continue
            if item["add"] and not item["error"]:
                new_slots[s["id"]] = item.pop("_slots")
            item.pop("_slots", None)
            items.append(item)
        out = {"week": lo, "to_week": dst.isoformat(), "items": items, "conflicts": self._capacity(sessions, new_slots, dst),
               "to_copy": sum(len(i["add"]) for i in items if not i["error"]), "applied": False, "copied": 0, "errors": []}
        if apply:
            out["applied"] = True
            for sid, slots in new_slots.items():
                try:
                    self.draft.execute(user, roles, sid, slots=slots)
                    out["copied"] += sum(len(i["add"]) for i in items if i["session"] == sid)
                except C.AiLiveError as e:
                    out["errors"].append({"session": sid, "error": str(e)})
        return out

    @staticmethod
    def _plan(s, slots, lo, hi):
        src = [x for x in slots if x.get("date") and lo <= x["date"] <= hi]
        if not src:
            return None
        have = {(x.get("date"), x["start"], x["end"]) for x in slots}
        add, dup = [], []
        for x in src:
            nd = (date.fromisoformat(x["date"]) + timedelta(days=7)).isoformat()
            y = dict(x, date=nd, days=[])
            (dup if (nd, x["start"], x["end"]) in have else add).append(y)
        item = {"session": s["id"], "title": s.get("title") or s["id"], "brand": s.get("brand") or "",
                "machine": P.draft_view(s)["machine"], "enabled": int(s.get("enabled") or 0),
                "add": [P.slot_text(y) + ("" if S.slot_on(y) else " (đang tắt)") for y in add],
                "dup": [P.slot_text(y) for y in dup], "error": "", "_slots": None}
        if add:
            try:
                norm = S.norm_slots(list(slots) + add)
                clash = S.self_overlap(norm, date.fromisoformat(lo))
                if clash:
                    raise C.AiLiveError(C.SessMsg.SLOT_OVERLAP % (clash[1], clash[0]))
                item["_slots"] = norm
            except C.AiLiveError as e:
                item["error"] = str(e)
        return item

    def _capacity(self, sessions, new_slots, dst):
        """Cho vuot so live cung luc o tuan dich NEU chep - chi bao cho dinh toi phien duoc chep."""
        groups = {}
        for s in sessions:
            v = P.draft_view(s)
            if int(s.get("enabled") or 0) and v["machine"]:
                groups.setdefault(v["machine"], []).append({"id": s["id"], "slots": new_slots.get(s["id"], v["slots"])})
        a, b = first_ts(dst), first_ts(dst) + 7 * 86400
        out = []
        for code, group in sorted(groups.items()):
            if not any(g["id"] in new_slots for g in group):
                continue
            m = self.machines.get(code) or {}
            cap = int(m.get("max_lives") or C.DEFAULT_MAX_LIVES)
            for c in S.capacity_conflicts(group, cap, dst):
                if a <= c["start"] < b and set(c["ids"]) & set(new_slots):
                    out.append({"machine": code, "at": c["start"], "ids": c["ids"], "max_lives": cap,
                                "text": C.SessMsg.COPY_OVER % (code, cap, datetime.fromtimestamp(c["start"], R._VN).strftime("%d/%m %H:%M"), ", ".join(c["ids"]))})
        return out
