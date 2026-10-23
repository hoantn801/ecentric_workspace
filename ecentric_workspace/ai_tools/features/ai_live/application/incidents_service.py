# Copyright (c) 2026, eCentric and contributors
"""Su co AI Live tren ERP (fix10h, B6): danh sach theo trang thai (Dang mo / Da xac nhan / Da xong) va xac nhan.
Xac nhan chi dung tin nhac lai + leo thang do ERP gui; tin app tu gui khong dung duoc. KHAN bat buoc ghi chu."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import incident_rules as I


class ListIncidentsService:
    def __init__(self, incidents=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.incidents = incidents or D.incidents()
        self.clock = clock or R.now_ts

    def execute(self, roles, status="open", days=7):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        st = C.INC_STATUS_KEYS.get(str(status or "open"))
        if not st:
            raise C.AiLiveError(C.IncMsg.BAD_STATUS)
        now, days = self.clock(), max(1, min(int(days or 7), 90))
        since = now - days * 86400
        rows = [I.view(x, now) for x in self.incidents.by_status(st, since)]
        if st != C.IncStatus.DONE:          # dang mo: KHAN + lau nhat len dau
            rows.sort(key=lambda r: (r["level"] != C.Level.CRIT, r["opened_ts"]))
        counts = self.incidents.counts(since)
        return {"status": status, "rows": rows, "days": days, "server_time": now,
                "counts": {k: counts.get(v, 0) for k, v in C.INC_STATUS_KEYS.items()}}


class AckIncidentService:
    def __init__(self, incidents=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.incidents = incidents or D.incidents()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, name, note=""):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        inc = self.incidents.get(str(name or ""))
        if not inc:
            raise C.AiLiveError(C.IncMsg.NOT_FOUND % name)
        if inc["status"] == C.IncStatus.DONE:
            raise C.AiLiveError(C.IncMsg.DONE)
        if inc["status"] == C.IncStatus.ACKED:
            raise C.AiLiveError(C.IncMsg.ACKED % (inc.get("acked_by") or "?"))
        note = str(note or "").strip()[:C.MAX_INC_NOTE]
        if inc["level"] == C.Level.CRIT and not note:
            raise C.AiLiveError(C.IncMsg.NEED_NOTE)
        now = self.clock()
        self.incidents.update(inc["name"], {"status": C.IncStatus.ACKED, "acked_by": user, "acked_ts": now, "ack_note": note})
        return I.view(dict(inc, status=C.IncStatus.ACKED, acked_by=user, acked_ts=now, ack_note=note), now)
