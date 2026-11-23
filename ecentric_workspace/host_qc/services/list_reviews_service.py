# Copyright (c) 2026, eCentric and contributors
"""reviews: app lay ket qua duyet tren ERP de ky thuat xem (app khong con nut duyet khi da noi ERP)."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.exceptions import ForbiddenError, NotFoundError
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.repositories.violation_repository import ViolationRepository
from ecentric_workspace.host_qc.utils.time import iso


class ListReviewsService:
    def __init__(self, sessions=None, violations=None):
        self.sessions = sessions or SessionRepository()
        self.violations = violations or ViolationRepository()

    def execute(self, machine, session_id):
        s = self.sessions.get_brief(str(session_id or ""))
        if not s:
            raise NotFoundError(M.NO_SESSION % session_id)
        if s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        return [{"violation_id": r["violation_id"], "review": r["review"], "reviewer": r.get("reviewed_by") or "",
                 "note": r.get("review_note") or "", "at": iso(r.get("reviewed_at"))}
                for r in self.violations.reviewed(s["name"])]
