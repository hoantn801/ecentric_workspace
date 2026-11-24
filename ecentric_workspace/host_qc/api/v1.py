# Copyright (c) 2026, eCentric and contributors
"""API AI Host QC - duong dan app goi: /api/method/ecentric_workspace.host_qc.api.v1.<ham>

May studio: allow_guest + header X-HostQC-Token: <machine_id>.<token> (xac thuc trong _guard.machine).
Nguoi dung ERP (Desk): dang nhap, kiem role trong service. Moi ham: guard -> service -> envelope."""
import frappe

from ecentric_workspace.host_qc.api import _guard as G
from ecentric_workspace.host_qc.api._envelope import run
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import CLIP_MAX_BYTES, TRANSCRIPT_MAX_BYTES

_SKIP = ("cmd", "data")


def _body(kw):
    return {k: G.obj(v) for k, v in kw.items() if k not in _SKIP}


# ------------------------------------------------------------------------------ may studio ---
@frappe.whitelist(allow_guest=True, methods=["POST"])
def heartbeat(**kw):
    from ecentric_workspace.host_qc.services.record_heartbeat_service import RecordHeartbeatService
    return run(lambda: RecordHeartbeatService().execute(G.machine(kw.get("machine_id")), _body(kw)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def next_session(**kw):
    from ecentric_workspace.host_qc.services.get_next_session_service import GetNextSessionService
    return run(lambda: GetNextSessionService().execute(G.machine(kw.get("machine_id")), kw.get("room_id")))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def list_rooms(**kw):
    from ecentric_workspace.host_qc.services.list_rooms_service import ListRoomsService
    return run(lambda: G.machine(kw.get("machine_id")) and ListRoomsService().execute())


@frappe.whitelist(allow_guest=True, methods=["GET"])
def rules(**kw):
    from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
    return run(lambda: G.machine() and BuildRulesConfigService().execute())


@frappe.whitelist(allow_guest=True, methods=["POST"])
def session_open(**kw):
    from ecentric_workspace.host_qc.services.open_session_service import OpenSessionService
    return run(lambda: OpenSessionService().execute(G.machine(kw.get("machine_id")), _body(kw)))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def violation(**kw):
    from ecentric_workspace.host_qc.services.record_violation_service import RecordViolationService
    return run(lambda: RecordViolationService().execute(G.machine(), _body(kw)))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def violation_clip(violation_id: str = None, **kw):
    from ecentric_workspace.host_qc.services.store_violation_clip_service import StoreViolationClipService
    return run(lambda: StoreViolationClipService().execute(G.machine(), violation_id,
                                                           G.upload("file", CLIP_MAX_BYTES)))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def score(session_id: str = None, score=None, **kw):
    from ecentric_workspace.host_qc.services.record_score_service import RecordScoreService
    return run(lambda: RecordScoreService().execute(G.machine(), session_id, G.obj(score)))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def alert(session_id: str = None, reason: str = None, violation_ids=None, score=None, **kw):
    from ecentric_workspace.host_qc.services.record_alert_service import RecordAlertService
    return run(lambda: RecordAlertService().execute(G.machine(), session_id, reason, G.obj(violation_ids),
                                                    G.obj(score)))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def session_close(**kw):
    from ecentric_workspace.host_qc.services.close_session_service import CloseSessionService
    return run(lambda: CloseSessionService().execute(G.machine(), _body(kw),
                                                     G.upload("transcript", TRANSCRIPT_MAX_BYTES)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def reviews(session_id: str = None, **kw):
    from ecentric_workspace.host_qc.services.list_reviews_service import ListReviewsService
    return run(lambda: ListReviewsService().execute(G.machine(), session_id))


# ------------------------------------------------------------------------- nguoi dung ERP ---
@frappe.whitelist(methods=["POST"])
def issue_machine_token(machine_id: str):
    from ecentric_workspace.host_qc.services.issue_machine_token_service import IssueMachineTokenService
    return run(lambda: IssueMachineTokenService().execute(machine_id, frappe.session.user, G.user_roles()),
               message=M.TOKEN_ISSUED)


@frappe.whitelist(methods=["GET"])
def machine_mics(machine_id: str = None, room_id: str = None):
    from ecentric_workspace.host_qc.services.machine_mics_service import MachineMicsService
    return run(lambda: MachineMicsService().execute(G.user_roles(), machine_id, room_id))


@frappe.whitelist(methods=["POST"])
def review_violation(violation_id: str, review: str, note: str = ""):
    from ecentric_workspace.host_qc.services.review_violation_service import ReviewViolationService
    return run(lambda: ReviewViolationService().execute(frappe.session.user, G.user_roles(), violation_id,
                                                        review, note or ""), message=M.REVIEW_SAVED)


@frappe.whitelist(methods=["GET"])
def guide():
    from ecentric_workspace.host_qc.services.get_guide_service import GetGuideService
    return run(lambda: GetGuideService().execute(G.user_roles()))
