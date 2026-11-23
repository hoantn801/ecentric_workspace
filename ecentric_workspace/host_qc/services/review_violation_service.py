# Copyright (c) 2026, eCentric and contributors
"""Duyet 1 loi tren ERP (3 nut tren form): Valid Violation / False Positive / Need Review + ghi chu.

Ghi lich su duyet, cap nhat co "cho xac minh" (Critical), roi tinh lai diem phien."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.roles import MANAGE
from ecentric_workspace.host_qc.constants.rules import TEXT_MAX
from ecentric_workspace.host_qc.constants.statuses import Review
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.violation_repository import ViolationRepository
from ecentric_workspace.host_qc.services.record_violation_service import needs_check
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService
from ecentric_workspace.host_qc.utils.time import now

ALLOWED = (Review.VALID.value, Review.FALSE_POSITIVE.value, Review.NEED_REVIEW.value)


class ReviewViolationService:
    def __init__(self, violations=None, rescore=None, clock=now):
        self.violations = violations or ViolationRepository()
        self.rescore = rescore or RescoreSessionService(violations=self.violations)
        self.clock = clock

    def execute(self, user, roles, violation_id, review, note=""):
        if not set(roles or ()) & set(MANAGE):
            raise ForbiddenError(M.NEED_MANAGER)
        if review not in ALLOWED:
            raise InvalidInput(M.BAD_REVIEW)
        v = self.violations.get(str(violation_id or ""))
        if not v:
            raise NotFoundError(M.NO_VIOLATION % violation_id)
        note = str(note or "").strip()[:TEXT_MAX]
        at = self.clock()
        self.violations.update(v["name"], {"review": review, "review_note": note, "reviewed_by": user,
                                           "reviewed_at": at, "needs_verification": needs_check(v["severity"], review)})
        self.violations.add_review_log(v["name"], {"at": at, "user": user, "from_review": v.get("review") or "",
                                                   "to_review": review, "note": note})
        score = self.rescore.execute(v["session"])
        return {"review": review, "total_score": (score or {}).get("total"), "status_color": (score or {}).get("status")}
