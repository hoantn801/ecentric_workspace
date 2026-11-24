# Copyright (c) 2026, eCentric and contributors
"""alert: app bao phien vua cham nguong. Khoa chong gui trung = phien + ly do + danh sach id loi.

Dot 1: chi ghi Host QC Alert Log (ok = 0). Dot 3 them gui Adaptive Card qua webhook Teams + thu lai."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.statuses import AlertReason
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.alert_log_repository import AlertLogRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.utils.time import now

REASONS = tuple(r.value for r in AlertReason)


def idem_key(session_id, reason, ids):
    return "%s|%s|%s" % (session_id, reason, ",".join(sorted(str(i) for i in ids)))[:140]


class RecordAlertService:
    def __init__(self, sessions=None, logs=None, clock=now):
        self.sessions = sessions or SessionRepository()
        self.logs = logs or AlertLogRepository()
        self.clock = clock

    def execute(self, machine, session_id, reason, violation_ids, score):
        s = self.sessions.get_brief(str(session_id or ""))
        if not s:
            raise NotFoundError(M.NO_SESSION % session_id)
        if s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        if reason not in REASONS:
            raise InvalidInput(M.BAD_REASON % reason)
        ids = [str(i) for i in (violation_ids or [])][:50]
        key = idem_key(s["name"], reason, ids)
        if self.logs.exists(key):
            return {"sent": False, "duplicate": True}
        total = score.get("total") if isinstance(score, dict) else score
        self.logs.insert({"session": s["name"], "reason": reason, "violations": "\n".join(ids),
                          "score": int(float(total or 0)), "sent_at": self.clock(), "ok": 0, "tries": 0,
                          "error": M.ALERT_NOT_SENT, "idem_key": key})
        return {"sent": False}
