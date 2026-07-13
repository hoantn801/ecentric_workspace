# Copyright (c) 2026, eCentric and contributors
"""Governed REQUESTER Submit & Sign lifecycle (Option B).

The requester signs BEFORE Approval Level 1 becomes actionable. This is NOT an approval
level: the request + frozen snapshot already exist (created at submit with
`activate_first_level=False`), Level 1 is inactive (no ToDo/notification), and only a
confirmed requester signature atomically activates Level 1 exactly once. The requester is
resolved dynamically from `EC Approval Request.requested_by`; identity comes only from the
requester's Active + Verified `EC SCTS User Mapping`; there is NO Administrator/System
Manager bypass. The approver path (approve_and_sign -> verify_and_complete -> engine.approve)
is untouched - a requester DSR carries `actor_type="Requester"` and completes here, never
through `engine.approve()`.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import events, guard, hashing
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms

DSR = "EC Digital Signature Request"
AR = "EC Approval Request"
PKG = "EC Digital Signature Package"
# request may (re)start requester signing from these states (retry-safe).
_START_STATES = ("Pending", "Reconciliation Required", "Failed")
# a DSR that still holds/represents a live or completed provider job.
_LIVE_OR_DONE = ("Draft", "Prepared", "Queued", "Provider Accepted", "Verifying",
                 "Signed", "Approval Completed")


def _profile_and_settings(business_doctype, approval_type):
    pname = guard.get_active_profile(business_doctype, approval_type)
    if not pname:
        return None, None, None
    prof = frappe.db.get_value("EC Digital Signature Profile", pname,
                               ["provider", "environment"], as_dict=True)
    st = frappe.db.get_value("EC Digital Signature Provider Settings",
                             {"provider": prof.provider, "environment": prof.environment},
                             "*", as_dict=True) or {}
    return pname, prof, st


def requester_signing_readiness(business_doctype, business_name):
    """Read-only, fail-closed readiness for the requester Submit & Sign action."""
    perms.assert_can_view_business(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    checks = {}
    if not ar:
        return {"ready": False, "reasons": ["not_submitted"], "checks": checks}
    req = frappe.db.get_value(AR, ar, ["approval_type", "current_level", "approval_status",
                                       "requester_signature_status", "requested_by"], as_dict=True)
    pname, prof, st = _profile_and_settings(business_doctype, req.approval_type)
    checks["signing_enabled"] = bool(pname)
    checks["requester_signature_required"] = bool(
        pname and guard.requester_signature_required(business_doctype, req.approval_type))
    checks["is_requester"] = frappe.session.user == req.requested_by
    checks["pending_requester_signature"] = req.requester_signature_status in _START_STATES
    mapping = perms.verified_mapping(req.requested_by, prof.environment) if prof else None
    checks["verified_mapping"] = bool(mapping)
    checks["provider_uat"] = bool(prof and prof.environment == "UAT")
    pkg_name = pkgsvc.active_package_for_request(ar)
    pkg = frappe.db.get_value(PKG, pkg_name, ["status", "package_hash"], as_dict=True) if pkg_name else None
    checks["package_active_hash_valid"] = bool(
        pkg and pkg.status == "Active" and pkg.package_hash
        and pkgsvc.compute_hash(pkg_name) == pkg.package_hash)
    checks["placements_complete"] = bool(pkg_name and not pkgsvc.preflight_for_lock(pkg_name))
    required = ["signing_enabled", "requester_signature_required", "is_requester",
                "pending_requester_signature", "verified_mapping", "provider_uat",
                "package_active_hash_valid", "placements_complete"]
    ready = all(checks.get(k) for k in required)
    return {"ready": ready, "reasons": [k for k in required if not checks.get(k)],
            "checks": checks, "current_status": req.requester_signature_status}


def requester_submit_and_sign(business_doctype, business_name, comment=None):
    """Governed requester Submit & Sign. Session user MUST be the authoritative requester
    (no admin/SM bypass); creates or reuses exactly one requester-scoped DSR under a request
    row lock; sets requester_signature_status=Processing; enqueues the signing worker."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    req = frappe.db.get_value(AR, ar, ["approval_type", "requester_signature_status",
                                       "requested_by"], as_dict=True)
    requester = req.requested_by
    if actor != requester:  # authoritative requester only; role is never a bypass
        frappe.throw(_("Chỉ người đề nghị mới được thực hiện Gửi & Ký."), frappe.PermissionError)
    pname, prof, st = _profile_and_settings(business_doctype, req.approval_type)
    if not pname or not guard.requester_signature_required(business_doctype, req.approval_type):
        frappe.throw(_("Loại yêu cầu này không yêu cầu chữ ký của người đề nghị."))
    if req.requester_signature_status == "Signed":
        frappe.throw(_("Người đề nghị đã ký cho yêu cầu này."))
    if req.requester_signature_status not in _START_STATES + ("Processing",):
        frappe.throw(_("Yêu cầu không ở trạng thái chờ ký của người đề nghị."))
    from ecentric_workspace.approval_center.esign import binding
    binding.assert_provider_uat(st)
    perms.assert_allowed_signer(st, requester)
    mapping = perms.verified_mapping(requester, prof.environment)
    if not mapping:
        events.emit("MappingRequired", erp_actor=requester,
                    request_meta={"business": business_name})
        frappe.throw(_("Người đề nghị chưa có ánh xạ chữ ký SCTS được xác minh."))
    pkg_name = pkgsvc.active_package_for_request(ar)
    if not pkg_name:
        frappe.throw(_("Không có gói tài liệu sẵn sàng ký."))
    pkg = frappe.db.get_value(PKG, pkg_name, ["name", "package_version", "package_hash"], as_dict=True)
    if pkgsvc.compute_hash(pkg_name) != pkg.package_hash:
        frappe.throw(_("Gói tài liệu đã thay đổi so với phiên bản đã khóa - cần phiên bản mới."))

    idem = hashing.idempotency_key(prof.provider, prof.environment, ar, "REQUESTER",
                                   requester, "RequesterSign", pkg.package_hash,
                                   "%s@%s" % (mapping.name, mapping.modified))
    frappe.db.get_value(AR, ar, "name", for_update=True)  # lock the request row
    existing = frappe.db.get_value(DSR, {"idempotency_key": idem}, ["name", "status"], as_dict=True)
    if existing and existing.status in _LIVE_OR_DONE:  # reuse - never duplicate a job/document
        frappe.db.set_value(AR, ar, {"requester_signature_status": "Processing",
                                     "requester_signature_request": existing.name})
        return {"signature_request": existing.name, "status": existing.status, "duplicate": True}

    dsr = frappe.get_doc({
        "doctype": DSR, "provider": prof.provider, "environment": prof.environment,
        "package": pkg_name, "approval_request": ar, "action": "Sign",
        "actor_type": "Requester", "actor_user": requester,
        "requested_by": requester, "approver": requester,
        "effective_scts_user_id": mapping.scts_user_id,
        "effective_signature_id": mapping.signature_id, "idempotency_key": idem,
        "status": "Draft", "package_version": pkg.package_version,
        "package_hash": pkg.package_hash,
    }).insert(ignore_permissions=True)  # post-authorization system row
    events.emit("RequesterSignatureSubmitted", signature_request=dsr.name, package=pkg_name,
                erp_actor=requester, scts_effective_user=mapping.scts_user_id)
    events.set_dsr_status(dsr.name, "Prepared", erp_actor=requester, event_type="Prepared")
    events.set_dsr_status(dsr.name, "Queued", extra_fields={"queued_at": now_datetime()},
                          erp_actor=requester)
    frappe.db.set_value(AR, ar, {"requester_signature_status": "Processing",
                                 "requester_signature_request": dsr.name})
    frappe.enqueue("ecentric_workspace.approval_center.esign.tasks.process_signing_request",
                   dsr_name=dsr.name, queue="default", timeout=600,
                   job_name="esign_requester_%s" % dsr.name, enqueue_after_commit=True)
    return {"signature_request": dsr.name, "status": "Queued", "duplicate": False}


def reconcile_and_complete_requester(dsr_name):
    """Worker/reconciliation completion for a Requester DSR. Maps the DSR terminal state to
    requester_signature_status and, on confirmed success ONLY, atomically activates Level 1.
    Never calls engine.approve(). Idempotent under repeated worker/poll/reconcile calls."""
    dsr = frappe.db.get_value(DSR, dsr_name,
                              ["name", "actor_type", "actor_user", "approval_request", "status"],
                              as_dict=True)
    if not dsr or dsr.actor_type != "Requester":
        return {"completed": False, "reason": "not_requester_dsr"}
    if dsr.status == "Signed":
        # promote to terminal + activate
        events.set_dsr_status(dsr_name, "Approval Completed",
                              extra_fields={"completed_at": now_datetime()},
                              event_type="RequesterSignatureConfirmed", verification_result="verified")
        return activate_level_one_after_requester_signature(dsr.approval_request, dsr_name)
    if dsr.status == "Approval Completed":
        return activate_level_one_after_requester_signature(dsr.approval_request, dsr_name)
    if dsr.status == "Permanent Failure":
        _set_req_status(dsr.approval_request, "Failed")
        events.emit("RequesterSignatureFailed", signature_request=dsr_name,
                    request_meta={"reason": "permanent_failure"})
        return {"completed": False, "reason": "failed"}
    if dsr.status in ("Verifying", "Retryable Failure", "Verification Mismatch", "Manual Review"):
        _set_req_status(dsr.approval_request, "Reconciliation Required")
        return {"completed": False, "reason": "reconciliation_required"}
    return {"completed": False, "reason": "in_progress:%s" % dsr.status}


def _set_req_status(ar, status):
    cur = frappe.db.get_value(AR, ar, "requester_signature_status")
    if cur != "Signed" and cur != status:  # never downgrade a completed requester signature
        frappe.db.set_value(AR, ar, "requester_signature_status", status)


def activate_level_one_after_requester_signature(request_name, dsr_name):
    """Idempotent atomic Level-1 activation. Level 1 activates ONLY when: requester signature
    is required, the confirmed requester DSR belongs to the authoritative requester, and the
    request is still in pre-approval (current_level == 0). Concurrent calls return the
    already-activated result without activating (or creating ToDos) twice."""
    frappe.db.get_value(AR, request_name, "name", for_update=True)  # lock
    req = frappe.db.get_value(AR, request_name,
                              ["approval_type", "reference_doctype", "current_level",
                               "requester_signature_status", "requested_by"], as_dict=True)
    if not req:
        return {"activated": False, "reason": "request_missing"}
    if not guard.requester_signature_required(req.reference_doctype, req.approval_type):
        return {"activated": False, "reason": "requester_signature_not_required"}
    d = frappe.db.get_value(DSR, dsr_name, ["actor_type", "actor_user", "status"], as_dict=True)
    if not d or d.actor_type != "Requester" or d.status != "Approval Completed" \
            or d.actor_user != req.requested_by:
        return {"activated": False, "reason": "requester_dsr_not_confirmed"}
    if req.requester_signature_status != "Signed":
        frappe.db.set_value(AR, request_name, {
            "requester_signature_status": "Signed", "requester_signed_at": now_datetime(),
            "requester_signed_by": req.requested_by})
    if req.current_level and int(req.current_level) > 0:  # already activated -> idempotent
        return {"activated": False, "reason": "already_activated", "level": req.current_level}
    from ecentric_workspace.approval_center.engine import service as engine
    req_doc = frappe.get_doc(AR, request_name)
    first = engine._request_levels(request_name)[0]
    engine._activate_level(req_doc, first.level_no)   # creates Level-1 ToDos + notification once
    events.emit("LevelOneActivatedAfterRequester", signature_request=dsr_name,
                erp_actor=req.requested_by,
                request_meta={"approval_request": request_name, "level": first.level_no})
    return {"activated": True, "level": first.level_no}
