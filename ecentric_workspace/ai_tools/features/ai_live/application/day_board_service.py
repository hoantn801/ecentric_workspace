# Copyright (c) 2026, eCentric and contributors
"""18/11 (hop dong lich live muc 8): kieu xem Bang + Timeline cua 1 ngay van hanh 06:00 -> 06:00 hom sau.
Ke hoach = ban DA PHAT HANH (dung cai may dang chay, ke ca lan dang giu gio cu) ghep bao cao app (push_slot_report).
Moi dong: brand, kenh (OBS / san), may, live, gio, thoi luong, trang thai (Sap toi / Dang live / Da xong / Lo /
Khong co bao cao), chip ket qua. Loc brand / may / san. Khung qua dem nam tron trong 1 dong (khong cat doi)."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application.schedule_actuals_service import planned_day
from ecentric_workspace.ai_tools.features.ai_live.domain import board_rules as B
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import slot_report_rules as SR


class DayBoardService:
    def __init__(self, sessions=None, reports=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.reports = reports or D.slot_reports()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, roles, day=None, brand=None, machine=None, platform=None):
        _common.require_role(roles, C.SCHEDULE_VIEW_ROLES, C.Msg.NEED_SCHEDULE_VIEW)
        now = self.clock()
        if day:
            try:
                d = date.fromisoformat(str(day)) if C.DATE_RE.match(str(day)) else None
            except ValueError:
                d = None
            if d is None:
                raise C.AiLiveError(C.SessMsg.BAD_DAY)
        else:                                   # truoc 06:00 van thuoc ngay van hanh hom truoc
            d = (datetime.fromtimestamp(now, R._VN) - timedelta(hours=B.DAY_START_H)).date()
        lo, hi = B.window(d)
        sessions = self.sessions.list()
        by_id = {s["id"]: s for s in sessions}
        days = [d - timedelta(days=1), d, d + timedelta(days=1)]
        planned = [p for k in days for p in planned_day(sessions, k, now)]
        reports = self.reports.for_dates([k.isoformat() for k in days])
        rows = [r for r in SR.match(planned, reports, now, lambda live: live in by_id) if B.overlaps(r, lo, hi)]
        labels = {m["machine_code"]: m.get("label") or "" for m in self.machines.sync_states()}
        out = []
        for r in rows:
            s = by_id.get(r["live"]) or {}
            st = B.status(r, now)
            out.append(dict(r, platform=(s.get("platform") or "").lower(), title=s.get("title") or r["title"],
                            brand=r.get("brand") or s.get("brand") or "", machine_label=labels.get(r["machine"], ""),
                            status=st, status_text=B.STATUS_TEXT[st], hours=round((r["end_ts"] - r["start_ts"]) / 3600.0, 2)))
        facets = {"brands": sorted({r["brand"] for r in out if r["brand"]}),
                  "machines": sorted({r["machine"] for r in out if r["machine"]} | set(labels)),
                  "platforms": sorted({r["platform"] for r in out if r["platform"]})}
        keep = [r for r in out if (not brand or r["brand"] == brand) and (not machine or r["machine"] == machine)
                and (not platform or r["platform"] == str(platform).lower())]
        counts = {k: sum(1 for r in keep if r["status"] == k and not (r["off_plan"] or r["stale_plan"])) for k in B.STATUS_TEXT}
        return {"day": d.isoformat(), "window": [lo, hi], "rows": keep, "summary": SR.summary(keep), "counts": counts,
                "facets": facets, "server_time": now, "now_text": R.vn_text(now),
                "can_edit": _common.has_role(roles, C.SCHEDULE_EDIT_ROLES),
                "today": datetime.fromtimestamp(now, R._VN).date().isoformat(), "drafts": sum(1 for s in sessions if s.get("draft"))}
