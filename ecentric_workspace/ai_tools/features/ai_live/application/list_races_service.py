# Copyright (c) 2026, eCentric and contributors
"""Trang "Dua vit" + tab "Giai thuong" cua chi tiet phien: danh sach cuoc dua (loc brand / live / khoang ngay /
ket qua / trang thai trao giai) kem nguoi thang, tong so; xuat CSV dung chung bo loc."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR


def _day(v, default):
    if not v:
        return default
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise C.AiLiveError(C.RaceMsg.BAD_DATE)


class ListRacesService:
    def __init__(self, races=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.races = races or DS.races()
        self.clock = clock or R.now_ts

    def query(self, roles, brand=None, live=None, date_from=None, date_to=None, outcome=None, prize=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        today = datetime.fromtimestamp(self.clock(), R._VN).date()
        d1 = _day(date_to, today)
        d0 = _day(date_from, d1 - timedelta(days=C.RACE_DEFAULT_DAYS - 1))
        if d0 > d1 or (d1 - d0).days >= C.RACE_MAX_DAYS:
            raise C.AiLiveError(C.RaceMsg.BAD_DATE)
        label = RR.prize_label(prize) if prize else None
        if prize and not label:
            raise C.AiLiveError(C.RaceMsg.BAD_STATUS)
        rows = self.races.list(d0.isoformat(), d1.isoformat(), brand or None, live or None,
                               outcome if outcome in C.RACE_OUTCOMES else None, C.RACE_LIST_MAX + 1)
        truncated = len(rows) > C.RACE_LIST_MAX
        rows = rows[:C.RACE_LIST_MAX]
        if label:
            rows = [r for r in rows if any(w["status"] == label for w in r["winners"])]
        for r in rows:
            for w in r["winners"]:
                w.pop("app_status", None)
                w.pop("app_note", None)
        return rows, d0, d1, truncated

    def execute(self, roles, brand=None, live=None, date_from=None, date_to=None, outcome=None, prize=None):
        rows, d0, d1, truncated = self.query(roles, brand, live, date_from, date_to, outcome, prize)
        ws = [w for r in rows for w in r["winners"]]
        totals = {"races": len(rows), "done": sum(1 for r in rows if r["outcome"] == "done"), "winners": len(ws),
                  "entrants": sum(r["entrants"] for r in rows)}
        totals.update({code: sum(1 for w in ws if w["status"] == lab) for code, lab in C.PRIZE_STATUS.items()})
        return {"races": rows, "totals": totals, "truncated": truncated, "date_from": d0.isoformat(), "date_to": d1.isoformat(),
                "brands": sorted({r["brand"] for r in rows if r["brand"]}), "lives": sorted({r["live"] for r in rows}),
                "statuses": C.PRIZE_STATUS, "outcomes": C.RACE_OUTCOMES, "by": C.RACE_BY, "server_time": self.clock()}
