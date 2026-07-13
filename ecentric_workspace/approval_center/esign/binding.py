# Copyright (c) 2026, eCentric and contributors
"""Strict ERP-side signer binding - the pre-write authorization gate for SCTS.

SCTS UAT security findings A-E proved SCTS does NOT safely enforce caller identity
(token<->user binding weak, GetSignatures authz weak, signature ownership not enforced).
Therefore ERP proves the ENTIRE identity chain itself and refuses the outbound call
unless every link holds:

    ERP active approver  ==  verified SCTS mapping  ==  outbound bulk-process userId
                         ==  owner of the selected signatureId (live GetSignatures)

`assert_outbound_binding` is called immediately BEFORE any SCTS write (bulk-process) on
every entry path (worker + orchestrator). It reads only PERSISTED rows under a DSR row
lock (never a caller-supplied snapshot, never frontend userId/signatureId) plus one LIVE
provider ownership probe. It fails closed on the first miss. There is NO role bypass:
Administrator / System Manager are subject to the identical chain.

Governed, sanitized audit events are appended for binding validated/rejected and
signature ownership validated/rejected. A transient provider error (network/5xx) raised
by the live ownership probe is NOT a binding rejection - it propagates with its original
retryable classification so an outage is never misclassified as a security failure.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"
SETTINGS_DT = "EC Digital Signature Provider Settings"
SUBMIT_ELIGIBLE = ("Queued", "Provider Accepted", "Verifying")


class BindingError(frappe.PermissionError):
    """Signer-binding refusal. Message carries a short, safe reason code."""


def _block(code):
    frappe.throw(_("Ràng buộc chữ ký thất bại - từ chối gọi nhà cung cấp.") + " [%s]" % code,
                 BindingError)


def _emit(dsr_name, actor, event_type, verification_result=None):
    """Best-effort sanitized audit event. Never blocks the security decision, never
    carries tokens/passwords/headers/raw bodies (events.emit sanitizes metadata)."""
    try:
        events.emit(event_type, signature_request=dsr_name, erp_actor=actor,
                    verification_result=verification_result)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.binding._emit")


def assert_provider_uat(settings):
    """This phase (S2B-A) signs against UAT only. Production is blocked outright - the
    write gate must never reach a Production provider regardless of other gates."""
    env = settings.get("environment") if isinstance(settings, dict) else getattr(
        settings, "environment", None)
    if env != "UAT":
        _block("provider_not_uat:%s" % env)


def assert_outbound_binding(dsr_name, adapter, live=True):
    """The authoritative pre-write gate. Returns True only if the full chain holds;
    otherwise raises BindingError (PermissionError) BEFORE any provider write, after
    emitting a sanitized BindingRejected event. When `live` is True, also proves
    signature ownership + usability via the adapter's GetSignatures probe (SCTS
    authorization is never trusted). A transient GetSignatures ProviderError propagates
    unchanged (availability failure, NOT a security rejection)."""
    if not dsr_name:
        _block("no_dsr")

    # Lock + read the persisted request (freshness + concurrency).
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    dsr = frappe.db.get_value(
        DSR, dsr_name,
        ["name", "provider", "environment", "action", "status", "approval_request",
         "request_level", "approver_row", "approver", "package", "package_version",
         "package_hash", "effective_scts_user_id", "effective_signature_id",
         "actor_type", "actor_user"], as_dict=True)
    if not dsr:
        _block("dsr_missing")

    try:
        _run_binding_checks(dsr, adapter, live)
    except BindingError as e:
        _emit(dsr_name, dsr.approver, "BindingRejected", safe_error(e)[:140])
        raise
    _emit(dsr_name, dsr.approver, "BindingValidated")
    return True


def _run_requester_binding_checks(dsr, adapter, live):
    """Requester-scoped binding: identity bound to the AUTHORITATIVE requester (actor_user),
    request in pre-approval (current_level == 0), NEVER approver row/level. Same fail-closed
    gate/allowlist/UAT/mapping-equality invariants as the approver path."""
    if dsr.action != "Sign":
        _block("dsr_wrong_action:%s" % dsr.action)
    if dsr.status not in SUBMIT_ELIGIBLE:
        _block("dsr_not_submit_eligible:%s" % dsr.status)
    if not dsr.actor_user:
        _block("requester_actor_missing")
    if not dsr.effective_scts_user_id or not dsr.effective_signature_id:
        _block("dsr_missing_effective_identity")
    settings = frappe.db.get_value(
        SETTINGS_DT, {"provider": dsr.provider, "environment": dsr.environment},
        ["name", "environment", "integration_enabled", "allow_signing",
         "allow_production_signing", "allowed_signing_users"], as_dict=True)
    if not settings:
        _block("settings_missing")
    assert_provider_uat(settings)
    if not settings.integration_enabled or not settings.allow_signing:
        _block("gates_closed")
    if settings.environment == "Production" and not settings.allow_production_signing:
        _block("production_signing_off")
    perms.assert_allowed_signer(settings, dsr.actor_user)
    mapping = perms.verified_mapping(dsr.actor_user, dsr.environment)
    if not mapping:
        _block("mapping_absent_or_unverified")
    if str(mapping.scts_user_id) != str(dsr.effective_scts_user_id):
        _block("outbound_userid_mismatch")
    if str(mapping.signature_id) != str(dsr.effective_signature_id):
        _block("outbound_signatureid_mismatch")
    req = frappe.db.get_value("EC Approval Request", dsr.approval_request,
                              ["approval_status", "requested_by", "requester_signature_status",
                               "current_level"], as_dict=True)
    if not req:
        _block("approval_request_missing")
    if req.approval_status != "Pending":
        _block("request_not_pending:%s" % req.approval_status)
    if str(dsr.actor_user) != str(req.requested_by):
        _block("actor_not_authoritative_requester")
    if req.requester_signature_status not in ("Pending", "Processing", "Reconciliation Required"):
        _block("requester_status_invalid:%s" % req.requester_signature_status)
    if req.current_level and int(req.current_level) > 0:
        _block("level_already_active")  # requester signs BEFORE Level 1


def _run_binding_checks(dsr, adapter, live):
    """The full invariant chain. Raises BindingError on the first miss. Live ownership
    failures emit SignatureOwnershipRejected; a transient provider error propagates."""
    if getattr(dsr, "actor_type", None) == "Requester":
        return _run_requester_binding_checks(dsr, adapter, live)
    dsr_name = dsr.name
    if dsr.action != "Sign":
        _block("dsr_wrong_action:%s" % dsr.action)
    if dsr.status not in SUBMIT_ELIGIBLE:
        _block("dsr_not_submit_eligible:%s" % dsr.status)
    if not dsr.effective_scts_user_id or not dsr.effective_signature_id:
        _block("dsr_missing_effective_identity")

    # Provider settings + gates + environment (UAT-only this phase).
    settings = frappe.db.get_value(
        SETTINGS_DT, {"provider": dsr.provider, "environment": dsr.environment},
        ["name", "environment", "integration_enabled", "allow_signing",
         "allow_production_signing", "allowed_signing_users"], as_dict=True)
    if not settings:
        _block("settings_missing")
    assert_provider_uat(settings)
    if not settings.integration_enabled or not settings.allow_signing:
        _block("gates_closed")
    if settings.environment == "Production" and not settings.allow_production_signing:
        _block("production_signing_off")  # defense in depth (UAT-only already enforced)

    # Allowlist (fail-closed; empty = nobody). Bound to the PERSISTED approver.
    perms.assert_allowed_signer(settings, dsr.approver)

    # Verified + active mapping for the bound approver; outbound identity must EQUAL it.
    mapping = perms.verified_mapping(dsr.approver, dsr.environment)
    if not mapping:
        _block("mapping_absent_or_unverified")
    if str(mapping.scts_user_id) != str(dsr.effective_scts_user_id):
        _block("outbound_userid_mismatch")
    if str(mapping.signature_id) != str(dsr.effective_signature_id):
        _block("outbound_signatureid_mismatch")

    # Approval request active at the DSR's level.
    req = frappe.db.get_value("EC Approval Request", dsr.approval_request,
                              ["name", "approval_status", "current_level", "reference_doctype",
                               "reference_name"], as_dict=True)
    if not req:
        _block("approval_request_missing")
    if req.approval_status != "Pending" or not req.current_level:
        _block("request_not_pending:%s" % req.approval_status)

    rl = frappe.db.get_value("EC Approval Request Level", dsr.request_level,
                             ["level_no", "approval_request", "level_status"], as_dict=True)
    if not rl or rl.approval_request != req.name:
        _block("request_level_mismatch")
    if rl.level_no != req.current_level:
        _block("level_not_current:%s!=%s" % (rl.level_no, req.current_level))
    if rl.level_status in ("Completed", "Approved", "Skipped", "Rejected", "Cancelled"):
        _block("level_not_active:%s" % rl.level_status)

    # Current approver row still Pending and owned by the bound approver.
    ar = frappe.db.get_value("EC Approval Request Approver", dsr.approver_row,
                             ["approver", "level_no", "status", "approval_request"], as_dict=True)
    if not ar or ar.approval_request != req.name or ar.approver != dsr.approver:
        _block("approver_row_mismatch")
    if ar.level_no != req.current_level:
        _block("approver_row_level_mismatch")
    if ar.status != "Pending":
        _block("approver_row_not_pending:%s" % ar.status)

    # Package: same business doc, Active, version + hash pinned, CURRENT file hashes match.
    pkg = frappe.db.get_value(
        "EC Digital Signature Package", dsr.package,
        ["name", "approval_request", "business_doctype", "business_name", "status",
         "package_version", "package_hash"], as_dict=True)
    if not pkg or pkg.approval_request != req.name:
        _block("package_mismatch")
    if pkg.status != "Active":
        _block("package_not_active:%s" % pkg.status)
    if pkg.business_doctype != req.reference_doctype or pkg.business_name != req.reference_name:
        _block("business_document_mismatch")
    if not pkg.package_hash or str(dsr.package_hash) != str(pkg.package_hash):
        _block("package_hash_mismatch")
    if int(dsr.package_version or 0) != int(pkg.package_version or -1):
        _block("package_version_mismatch")
    if pkgsvc.compute_hash(pkg.name) != pkg.package_hash:
        _block("file_hash_drift")  # current file bytes/order/flags differ from approved

    # No other level completion already in place (duplicate write guard).
    other = frappe.db.exists(DSR, {"approval_request": req.name,
                                   "request_level": dsr.request_level,
                                   "status": "Approval Completed", "name": ["!=", dsr.name]})
    if other:
        _block("level_already_completed_by:%s" % other)

    # LIVE ownership + usability probe (never trust SCTS-side authorization). A transient
    # provider error PROPAGATES (retryable availability failure, not a security refusal).
    if live and adapter is not None:
        vr = adapter.validate_signature_owner(dsr.effective_scts_user_id,
                                              dsr.effective_signature_id)
        if not vr:
            reason = getattr(vr, "reason", "unverified")
            _emit(dsr_name, dsr.approver, "SignatureOwnershipRejected", reason)
            _block("signature_owner:%s" % reason)
        _emit(dsr_name, dsr.approver, "SignatureOwnershipValidated", "verified_owner")
