# Copyright (c) 2026, eCentric and contributors
"""Lich live 1 tuan (thu Hai -> Chu nhat): moi khung cua moi phien thanh 1 khoi tren lan may (hoac brand);
khoi nao lam may vuot so live toi da cung luc -> danh dau trung."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


def week_start(week, now):
    """Chuoi YYYY-MM-DD (bat ky ngay nao trong tuan) hoac rong -> ngay thu Hai cua tuan."""
    if week:
        if not C.DATE_RE.match(str(week)):
            raise C.AiLiveError(C.SessMsg.BAD_WEEK)
        d = date.fromisoformat(str(week))
    else:
        d = datetime.fromtimestamp(now, R._VN).date()
    return d - timedelta(days=d.isoweekday() - 1)


class WeekScheduleService:
    def __init__(self, sessions=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, roles, week=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now = self.clock()
        mon = week_start(week, now)
        days = [mon + timedelta(days=k) for k in range(7)]
        sessions = self.sessions.list()
        machines = {m["machine_code"]: m for m in self.machines.all()}
        blocks = []
        for s in sessions:
            for a, b, i in S.occurrences(s["slots"], days):
                blocks.append({"session": s["id"], "slot": i, "date": datetime.fromtimestamp(a, R._VN).date().isoformat(),
                               "start_ts": a, "end_ts": b, "start": s["slots"][i]["start"], "end": s["slots"][i]["end"],
                               "recurring": not s["slots"][i]["date"], "enabled": s["enabled"], "conflict": False})
        conflicts = self._conflicts(sessions, machines, days, blocks)
        return {"week": mon.isoformat(), "days": [d.isoformat() for d in days], "today": datetime.fromtimestamp(now, R._VN).date().isoformat(),
                "sessions": [{k: s[k] for k in ("id", "title", "brand", "platform", "machine", "enabled", "slots")} for s in sessions],
                "machines": [{"code": c, "label": m["label"], "max_lives": m["max_lives"]} for c, m in machines.items()],
                "blocks": blocks, "conflicts": conflicts, "server_time": now}

    def _conflicts(self, sessions, machines, days, blocks):
        out = []
        by_machine = {}
        for s in sessions:
            if s["enabled"] and s["machine"]:
                by_machine.setdefault(s["machine"], []).append({"id": s["id"], "slots": s["slots"]})
        lo = datetime(days[0].year, days[0].month, days[0].day, tzinfo=R._VN).timestamp()
        hi = lo + 7 * 86400
        for code, group in by_machine.items():
            cap = (machines.get(code) or {}).get("max_lives") or C.DEFAULT_MAX_LIVES
            for c in S.capacity_conflicts(group, cap, days[0]):
                if not (lo <= c["start"] < hi):
                    continue
                out.append({"machine": code, "at": c["start"], "ids": c["ids"], "max_lives": cap})
                for b in blocks:
                    if b["session"] in c["ids"] and b["start_ts"] <= c["start"] < b["end_ts"]:
                        b["conflict"] = True
        return out
