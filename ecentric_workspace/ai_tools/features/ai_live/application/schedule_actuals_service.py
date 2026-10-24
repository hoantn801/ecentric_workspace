# Copyright (c) 2026, eCentric and contributors
"""Ke hoach vs thuc te 1 ngay (fix10h, B3 / 11.3): moi khung ke hoach ERP (ban dang phat hanh, ke ca lan dang giu
gio cu) ghep voi bao cao app gui (push_slot_report) theo (live, planned_start). Qua gio bat dau 15 phut ma khong
co bao cao -> "Khong co bao cao (may im lang?)"; bao cao khong khop khung nao -> "Ke hoach cu / lich tren may"
hoac "Ngoai ke hoach ERP"."""
from datetime import date, datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.features.ai_live.domain import slot_report_rules as SR


def planned_day(sessions, day, now):
    """[{live, title, brand, machine, obs_port, start_ts, end_ts}] - khung ke hoach bat dau trong ngay `day` (gio VN)."""
    day_lo = datetime(day.year, day.month, day.day, tzinfo=R._VN).timestamp()
    out = []
    for s in sessions:
        if not s.get("enabled"):
            continue
        v, held = P.published_view(s), None
        if float(s.get("held_until_ts") or 0) > day_lo and s.get("prev"):
            occ = P.occurrence_at(s["prev"]["slots"], float(s["held_until_ts"]) - 1)
            if occ and day_lo <= occ[0] < day_lo + 86400:
                held = occ
                out.append(_row(s, s["prev"], occ))
        for occ in S.occurrences(v["slots"], [day]):
            if held and occ[0] < held[1] and held[0] < occ[1]:
                continue
            out.append(_row(s, v, occ))
    return out


def _row(s, v, occ):
    return {"live": s["id"], "title": s.get("title") or s["id"], "brand": s.get("brand") or "",
            "machine": v.get("machine") or "", "obs_port": int(v.get("obs_port") or 0), "start_ts": occ[0], "end_ts": occ[1]}


class ScheduleActualsService:
    def __init__(self, sessions=None, reports=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.reports = reports or D.slot_reports()
        self.clock = clock or R.now_ts

    def execute(self, roles, day=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now = self.clock()
        if day and not C.DATE_RE.match(str(day)):
            raise C.AiLiveError(C.SessMsg.BAD_WEEK)
        d = date.fromisoformat(str(day)) if day else datetime.fromtimestamp(now, R._VN).date()
        return dict(self.compute(d, now), date=d.isoformat(), server_time=now)

    def compute(self, d, now):
        sessions = self.sessions.list()
        ids = {s["id"] for s in sessions}
        rows = SR.match(planned_day(sessions, d, now), self.reports.for_dates([d.isoformat()]), now, lambda live: live in ids)
        by_id = {s["id"]: s for s in sessions}
        for r in rows:
            s = by_id.get(r["live"])
            if r["stale_plan"] and s:            # ke hoach cu: hien dung dong kenh OBS + ten phien hien tai
                r.update(title=s.get("title") or r["live"], obs_port=int(P.published_view(s)["obs_port"] or 0),
                         machine=r["machine"] or P.published_view(s)["machine"])
        return {"rows": rows, "summary": SR.summary(rows)}
