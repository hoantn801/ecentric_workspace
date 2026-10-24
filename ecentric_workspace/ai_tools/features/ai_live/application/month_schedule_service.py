# Copyright (c) 2026, eCentric and contributors
"""fix10g: man Thang cua Lich live - moi ngay: so lan live, so gio, may vuot so live toi da, vai khung noi bat;
tong gio theo brand / may; % thoi gian may co live. View "draft" (mac dinh) hoac "published"."""
import calendar
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import load_rules as L
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P


class MonthScheduleService:
    def __init__(self, sessions=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, roles, month=None, view="draft"):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now = self.clock()
        y, m = self._month(month, now)
        first = date(y, m, 1)
        grid0 = first - timedelta(days=first.isoweekday() - 1)          # thu Hai dau luoi
        n_days = calendar.monthrange(y, m)[1]
        weeks = -(-((first - grid0).days + n_days) // 7)
        grid = [grid0 + timedelta(days=k) for k in range(weeks * 7)]
        sessions = self.sessions.list()
        machines = {x["machine_code"]: x for x in self.machines.sync_states()}
        views = {s["id"]: dict(P.draft_view(s) if view != "published" else P.published_view(s), enabled=s["enabled"])
                 for s in sessions}
        meta = {s["id"]: {"title": s["title"], "brand": s["brand"]} for s in sessions}
        days, _, _ = L.day_load(views, meta, machines, grid)
        in_month = [d for d in grid if d.month == m]
        _, brand_h, mach_h = L.day_load(views, meta, machines, in_month)
        for row in days:
            row["in_month"] = row["date"][:7] == "%04d-%02d" % (y, m)
        util = [{"code": c, "label": x["label"], "hours": mach_h.get(c, 0), "max_lives": x["max_lives"],
                 "pct": round(100 * mach_h.get(c, 0) / (24.0 * n_days * max(1, x["max_lives"])), 1)}
                for c, x in machines.items() if x["enabled"]]
        return {"month": "%04d-%02d" % (y, m), "today": datetime.fromtimestamp(now, R._VN).date().isoformat(),
                "view": view, "days": days, "brand_hours": brand_h, "machine_util": util,
                "total_hours": round(sum(brand_h.values()), 1), "over_days": sum(1 for d in days if d["in_month"] and d["over"]),
                "drafts": sum(1 for s in sessions if s.get("draft")), "server_time": now}

    @staticmethod
    def _month(v, now):
        if not v:
            d = datetime.fromtimestamp(now, R._VN)
            return d.year, d.month
        s = str(v)
        if len(s) != 7 or s[4] != "-" or not (s[:4].isdigit() and s[5:].isdigit()) or not 1 <= int(s[5:]) <= 12:
            raise C.AiLiveError(C.PubMsg.BAD_MONTH)
        return int(s[:4]), int(s[5:])
