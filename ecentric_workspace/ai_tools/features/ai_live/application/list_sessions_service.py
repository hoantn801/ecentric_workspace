# Copyright (c) 2026, eCentric and contributors
"""Trang Phien live: moi phien tren moi may (brand, san, may, trang thai dang live / co lich / tat / co van de,
khung ke tiep, nguoi xem, chi phi hom nay). Loc theo brand / san / may / trang thai."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._session_view import STATUS_ORDER, health_index, summarize
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R

STATUSES = (C.SessionStatus.PROBLEM, C.SessionStatus.ON_AIR, C.SessionStatus.SCHEDULED, C.SessionStatus.OFF)


class ListSessionsService:
    def __init__(self, sessions=None, health=None, settings=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as DM
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.health = health or DM.health()
        self.settings = settings or DM.settings()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, roles, brand=None, platform=None, machine=None, status=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now, cfg = self.clock(), self.settings.get()
        hi = health_index(self.health.all())
        rows = [summarize(s, hi.get(R.key_of(s["machine"], s["id"])) if s["machine"] else None, now, cfg)
                for s in self.sessions.list()]
        counts = {k: sum(1 for r in rows if r["status"] == k) for k in STATUSES}
        counts["total"] = len(rows)
        facets = {"brands": sorted({r["brand"] for r in rows if r["brand"]}),
                  "platforms": sorted({r["platform"] for r in rows if r["platform"]}),
                  "machines": [{"code": m["machine_code"], "label": m["label"], "max_lives": m["max_lives"]}
                               for m in self.machines.all()]}
        if brand:
            rows = [r for r in rows if r["brand"] == brand]
        if platform:
            rows = [r for r in rows if r["platform"] == platform]
        if machine:
            rows = [r for r in rows if r["machine"] == machine]
        if status in STATUSES:
            rows = [r for r in rows if r["status"] == status]
        rows.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9), (r["next"] or {}).get("start") or 9e12, r["title"]))
        return {"sessions": rows, "counts": counts, "facets": facets, "server_time": now, "refresh_s": 15}
