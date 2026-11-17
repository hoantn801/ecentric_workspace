# Copyright (c) 2026, eCentric and contributors
"""18/11 (hop dong lich live muc 8): kieu xem Theo brand trong thang - so lan live, gio ke hoach, gio da live
(theo bao cao app, tru gian doan), % hoan thanh so voi gio ke hoach DA TOI GIO. Ke hoach = ban da phat hanh."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application.schedule_actuals_service import planned_day
from ecentric_workspace.ai_tools.features.ai_live.domain import board_rules as B
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class BrandMonthService:
    def __init__(self, sessions=None, reports=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.reports = reports or D.slot_reports()
        self.clock = clock or R.now_ts

    def execute(self, roles, month=None, platform=None, machine=None):
        _common.require_role(roles, C.SCHEDULE_VIEW_ROLES, C.Msg.NEED_SCHEDULE_VIEW)
        now = self.clock()
        days = B.month_days(month, datetime.fromtimestamp(now, R._VN).date())
        every = self.sessions.list()
        facets = {"platforms": sorted({(s.get("platform") or "").lower() for s in every} - {""}),
                  "machines": sorted({s.get("machine") or "" for s in every} - {""})}
        sessions = [s for s in every if (not platform or (s.get("platform") or "").lower() == str(platform).lower())]
        by_id = {s["id"]: s for s in sessions}
        planned = [p for d in days for p in planned_day(sessions, d, now) if not machine or p["machine"] == machine]
        reports = [r for r in self.reports.for_dates([d.isoformat() for d in days], limit=C.MAX_MONTH_REPORTS)
                   if (not machine or r.get("machine") == machine) and (not platform or r.get("live") in by_id)]
        rows = B.brand_rollup(planned, reports, lambda live, rep: (by_id.get(live) or {}).get("brand") or rep.get("brand"), now)
        tot = {k: round(sum(r[k] for r in rows), 1) for k in ("planned_h", "due_h", "live_h", "off_plan_h")}
        tot["lives"] = sum(r["lives"] for r in rows)
        tot["pct"] = round(100.0 * tot["live_h"] / tot["due_h"]) if tot["due_h"] else None
        return {"month": days[0].strftime("%Y-%m"), "rows": rows, "total": tot, "facets": facets, "server_time": now, "can_edit": _common.has_role(roles, C.SCHEDULE_EDIT_ROLES),
                "today": datetime.fromtimestamp(now, R._VN).date().isoformat(), "drafts": sum(1 for s in every if s.get("draft"))}
