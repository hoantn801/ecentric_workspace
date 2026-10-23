# Copyright (c) 2026, eCentric and contributors
"""Lich live theo khoang ngay (1..7 ngay; mac dinh ca tuan thu Hai -> Chu nhat): moi khung cua moi phien thanh
1 khoi tren lan may (hoac brand); khoi lam may vuot so live toi da cung luc -> danh dau trung.
fix10g: view "draft" (mac dinh) = ban nhap ghep len ban phat hanh (khoi cua phien co nhap danh dau draft/changed);
"published" = dung ban app dang nhan. Lan dang giu gio cu hien thanh khoi held. Kem trang thai nhan lich tung may."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


def week_start(week, now):
    """Chuoi YYYY-MM-DD (bat ky ngay nao trong tuan) hoac rong -> ngay thu Hai cua tuan."""
    return _day(week, now) - timedelta(days=_day(week, now).isoweekday() - 1)


def _day(v, now):
    if v:
        if not C.DATE_RE.match(str(v)):
            raise C.AiLiveError(C.SessMsg.BAD_WEEK)
        return date.fromisoformat(str(v))
    return datetime.fromtimestamp(now, R._VN).date()


class WeekScheduleService:
    def __init__(self, sessions=None, machines=None, clock=None, schedule=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts
        self._schedule = schedule

    def execute(self, roles, week=None, days=7, start=None, view="draft"):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now, n = self.clock(), int(days or 7)
        if not 1 <= n <= 7:
            raise C.AiLiveError(C.PubMsg.BAD_DAYS)
        first = _day(start, now) if (start or n < 7) else week_start(week, now)
        span = [first + timedelta(days=k) for k in range(n)]
        sessions = self.sessions.list()
        states = self.machines.sync_states()
        machines = {m["machine_code"]: m for m in states}
        views = {s["id"]: dict(P.draft_view(s) if view != "published" else P.published_view(s), enabled=s["enabled"])
                 for s in sessions}
        blocks = []
        for s in sessions:
            v, pub = views[s["id"]], P.published_view(s)
            held = P.served_view(s, now) if s.get("held_until_ts", 0) > now and s.get("prev") else None
            hold_win = None
            if held:
                occ = P.occurrence_at(held["slots"], s["held_until_ts"] - 1)
                if occ and occ[0] < first_ts(span[-1]) + 86400 and occ[1] > first_ts(span[0]):
                    hold_win = occ[:2]
                    blocks.append(self._block(s, held, occ, held_until=s["held_until_ts"], why=s.get("held_why")))
            pub_keys = {(a, b) for a, b, _ in S.occurrences(pub["slots"], span)} if pub["machine"] == v["machine"] else set()
            for occ in S.occurrences(v["slots"], span):
                if hold_win and occ[0] < hold_win[1] and hold_win[0] < occ[1]:
                    continue                                   # lan nay van chay theo gio cu
                b = self._block(s, v, occ)
                b["changed"] = bool(s.get("draft")) and view != "published" and (occ[0], occ[1]) not in pub_keys
                blocks.append(b)
        conflicts = self._conflicts(views, machines, span, blocks)
        version = self._sched().settings()["version"]
        dead = C.DEAD_MAN_MIN * 60
        return {"week": span[0].isoformat(), "start": span[0].isoformat(), "days": [d.isoformat() for d in span],
                "today": datetime.fromtimestamp(now, R._VN).date().isoformat(), "view": view, "version": version,
                "sessions": [dict({k: s[k] for k in ("id", "title", "brand", "platform", "enabled")}, slots=views[s["id"]]["slots"],
                                  machine=views[s["id"]]["machine"], obs_port=views[s["id"]]["obs_port"],
                                  published_machine=s["machine"], draft_state=P.draft_state(s),
                                  diff=P.diff_texts(P.published_view(s), P.draft_view(s)) if s.get("draft") else [])
                             for s in sessions],
                "machines": [{"code": c, "label": m["label"], "max_lives": m["max_lives"], "enabled": m["enabled"],
                              "sync": P.machine_sync(m, sessions, now, dead)} for c, m in machines.items()],
                "drafts": sum(1 for s in sessions if s.get("draft")),
                "blocks": blocks, "conflicts": conflicts, "server_time": now}

    def _sched(self):
        if self._schedule is None:
            from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
            self._schedule = DS.schedule()
        return self._schedule

    @staticmethod
    def _block(s, v, occ, held_until=0, why=""):
        a, b, i = occ
        slot = v["slots"][i]
        return {"session": s["id"], "slot": i, "date": datetime.fromtimestamp(a, R._VN).date().isoformat(),
                "start_ts": a, "end_ts": b, "start": slot["start"], "end": slot["end"], "recurring": not slot["date"],
                "enabled": s["enabled"], "machine": v["machine"], "obs_port": int(v["obs_port"] or 0), "conflict": False,
                "changed": False, "held": bool(held_until), "held_until": held_until, "held_why": why or ""}

    @staticmethod
    def _conflicts(views, machines, span, blocks):
        out, groups = [], {}
        for sid, v in views.items():
            if v["enabled"] and v["machine"]:
                groups.setdefault(v["machine"], []).append({"id": sid, "slots": v["slots"]})
        lo, hi = first_ts(span[0]), first_ts(span[-1]) + 86400
        for code, group in groups.items():
            cap = (machines.get(code) or {}).get("max_lives") or C.DEFAULT_MAX_LIVES
            for c in S.capacity_conflicts(group, cap, span[0]):
                if not (lo <= c["start"] < hi):
                    continue
                out.append({"machine": code, "at": c["start"], "ids": c["ids"], "max_lives": cap})
                for b in blocks:
                    if b["session"] in c["ids"] and not b["held"] and b["start_ts"] <= c["start"] < b["end_ts"]:
                        b["conflict"] = True
        return out


def first_ts(d):
    return datetime(d.year, d.month, d.day, tzinfo=R._VN).timestamp()
