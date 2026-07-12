# Copyright (c) 2026, eCentric and contributors
"""Digital Signature Orchestrator.

Owns: pre-flight authorization, idempotency + concurrency, DSR lifecycle, provider
handoff (via adapter), verification, and the ONLY completion path into the engine:
engine.service.approve() called with the in-process call marker set AND a persisted,
provider-verified DSR that esign.guard re-validates against the DB under lock.

Never: raw approval-state writes, provider payloads (adapter-only), frontend-supplied
identity (mapping-only), completion on 'accepted' (three-concept separation).
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import binding, events, guard, hashing
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign.providers import get_adapter
from ecentric_workspace.approval_center.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"
LIVE_OR_DONE = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Signed",
                "Approval Completed")


# --------------------------------------------------------------------------- #
# resolution helpers
# --------------------------------------------------------------------------- #
def _settings_for(profile_row):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": profile_row.provider,
                             "environment": profile_row.environment}, "*", as_dict=True)
    if not s:
        frappe.throw(_("Chưa cấu hình Provider Settings cho {0}/{1}.").format(
            profile_row.provider, profile_row.environment))
    return s


def _profile_doc(reference_doctype, approval_type):
    name = guard.get_active_profile(reference_doctype, approval_type)
    if not name:
        frappe.throw(_("Ký số chưa được bật cho loại yêu cầu này."))
    return frappe.db.get_value("EC Digital Signature Profile", name, "*", as_dict=True)


def _req_for_business(business_doctype, business_name):
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Yêu cầu này chưa được gửi duyệt."))
    return frappe.get_doc("EC Approval Request", ar)


def _level_row(req):
    n = frappe.db.get_value("EC Approval Request Level",
                            {"approval_request": req.name, "level_no": req.current_level},
                            "name")
    if not n:
        frappe.throw(_("Không tìm thấy cấp duyệt hiện tại."))
    return n


def _profile_level(profile_name, level_no):
    return frappe.db.get_value("EC Digital Signature Profile Level",
                               {"parent": profile_name, "level_no": level_no},
                               ["requires_signature", "scts_role_title", "signature_type"],
                               as_dict=True)


def _transition_id(profile_name, action):
    return frappe.db.get_value("EC Digital Signature Profile Transition",
                               {"parent": profile_name, "action": action}, "transition_id")


def _lock_key(approval_request, level_no):
    return "esign:lock:%s:%s" % (approval_request, level_no)


def _acquire_lock(key):
    """Redis nx lock (alerts precedent). UX-independent server-side double-submit
    control; unique idempotency key remains the DB-level backstop."""
    try:
        ok = frappe.cache().set(key, "1", nx=True, ex=30)
    except Exception:
        ok = True  # cache down: unique idempotency key still guarantees single submission
    if not ok:
        frappe.throw(_("Yêu cầu ký đang được xử lý - vui lòng đợi."))


def _release_lock(key):
    try:
        frappe.cache().delete(key)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# approve & sign (single request)
# --------------------------------------------------------------------------- #
def approve_and_sign(business_doctype, business_name, comment=None, bulk_batch_key=None):
    """Full server-side pre-flight, then create+enqueue a signing request. The client
    supplied ONLY (business doctype, name, comment) - identity, level, package and
    transition are all resolved server-side."""
    actor = frappe.session.user
    req = _req_for_business(business_doctype, business_name)
    profile = _profile_doc(business_doctype, req.approval_type)
    settings = _settings_for(profile)

    binding.assert_provider_uat(settings)  # S2B-A: fail fast; Production blocked at submit
    perms.assert_allowed_signer(settings, actor)
    perms.assert_pending_approver(req, actor)
    approver_row = perms.pending_approver_row(req.name, req.current_level, actor)

    plevel = _profile_level(profile.name, req.current_level)
    if not plevel or not plevel.requires_signature:
        frappe.throw(_("Cấp duyệt hiện tại không yêu cầu ký số - dùng nút Duyệt thường."))

    mapping = perms.verified_mapping(actor, profile.environment)
    if not mapping:
        events.emit("MappingRequired", erp_actor=actor,
                    request_meta={"business": business_name, "level": req.current_level})
        frappe.throw(_("Bạn chưa có ánh xạ chữ ký SCTS được xác minh - liên hệ quản trị."))

    pkg_name = pkgsvc.active_package_for_request(req.name)
    if not pkg_name:
        frappe.throw(_("Không có gói tài liệu sẵn sàng ký cho yêu cầu này."))
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "package_version", "package_hash", "scts_document_id"],
                              as_dict=True)
    recomputed = pkgsvc.compute_hash(pkg_name)
    if recomputed != pkg.package_hash:
        events.emit("VerificationMismatch", package=pkg_name, erp_actor=actor,
                    verification_result="package_hash_drift")
        frappe.throw(_("Gói tài liệu đã thay đổi so với phiên bản đã khóa - cần phiên bản mới."))

    request_level = _level_row(req)
    idem = hashing.idempotency_key(
        profile.provider, profile.environment, req.name, request_level, approver_row,
        "Sign", pkg.package_hash, "%s@%s" % (mapping.name, mapping.modified))

    existing = frappe.db.get_value(DSR, {"idempotency_key": idem},
                                   ["name", "status"], as_dict=True)
    if existing and existing.status in LIVE_OR_DONE:
        return {"signature_request": existing.name, "status": existing.status,
                "duplicate": True}

    lock = _lock_key(req.name, req.current_level)
    _acquire_lock(lock)
    try:
        # Backstop re-check inside the lock window.
        existing = frappe.db.get_value(DSR, {"idempotency_key": idem},
                                       ["name", "status"], as_dict=True)
        if existing and existing.status in LIVE_OR_DONE:
            return {"signature_request": existing.name, "status": existing.status,
                    "duplicate": True}
        if existing:  # prior terminal-failed attempt: reuse row, bump attempt
            dsr_name = existing.name
            frappe.db.set_value(DSR, dsr_name, {
                "request_attempt": (frappe.db.get_value(DSR, dsr_name, "request_attempt") or 0) + 1,
                "requested_by": actor})
            events.set_dsr_status(dsr_name, "Prepared", event_type="RetryScheduled",
                                  erp_actor=actor)
        else:
            dsr = frappe.get_doc({
                "doctype": DSR, "provider": profile.provider,
                "environment": profile.environment, "package": pkg_name,
                "approval_request": req.name, "request_level": request_level,
                "approver_row": approver_row, "action": "Sign",
                "requested_by": actor, "approver": actor,
                "effective_scts_user_id": mapping.scts_user_id,
                "effective_signature_id": mapping.signature_id,
                "idempotency_key": idem, "status": "Draft",
                "package_version": pkg.package_version, "package_hash": pkg.package_hash,
                "bulk_batch_key": bulk_batch_key,
            }).insert(ignore_permissions=True)  # post-authorization system row
            dsr_name = dsr.name
            events.emit("Created", signature_request=dsr_name, package=pkg_name,
                        erp_actor=actor, scts_effective_user=mapping.scts_user_id)
            events.set_dsr_status(dsr_name, "Prepared", erp_actor=actor,
                                  event_type="Prepared")
        events.set_dsr_status(dsr_name, "Queued",
                              extra_fields={"queued_at": now_datetime()}, erp_actor=actor)
        frappe.enqueue(
            "ecentric_workspace.approval_center.esign.tasks.process_signing_request",
            dsr_name=dsr_name, queue="default", timeout=600,
            job_name="esign_dsr_%s" % dsr_name, enqueue_after_commit=True)
        return {"signature_request": dsr_name, "status": "Queued", "duplicate": False}
    finally:
        _release_lock(lock)


# --------------------------------------------------------------------------- #
# verification + completion (worker side)
# --------------------------------------------------------------------------- #
def _expected_for(dsr):
    pkg = frappe.db.get_value("EC Digital Signature Package", dsr.package,
                              ["scts_document_id"], as_dict=True)
    file_count = frappe.db.count("EC Digital Signature File", {"package": dsr.package})
    return {"document_id": pkg.scts_document_id, "user_id": dsr.effective_scts_user_id,
            "signature_id": dsr.effective_signature_id, "file_count": file_count}


def mark_verified(dsr_name, doc_state):
    """Provider state passed verify_signed_result -> DSR Signed + verified_at."""
    events.set_dsr_status(dsr_name, "Signed",
                          extra_fields={"verified_at": now_datetime()},
                          event_type="Verified", verification_result="verified")



def _guarded_dsr_transition(dsr_name, from_status, to_status, extra=None,
                            event_type=None, **event_kw):
    """R2 (2026-07-12): race-safe conditional state mutation - the CURRENT persisted
    status is part of the UPDATE condition, so a worker that lost a completion race
    can never overwrite another worker's terminal result (Approval Completed is
    never downgraded). Returns True only if THIS caller performed the transition;
    the audit event is emitted only in that case (no misleading failure events for
    idempotent losers)."""
    from ecentric_workspace.approval_center.esign import state as sm
    sm.assert_transition(sm.DSR, from_status, to_status)
    vals = {"status": to_status}
    vals.update(extra or {})
    set_clause = ", ".join("`%s`=%%s" % k for k in vals)
    frappe.db.sql("UPDATE `tabEC Digital Signature Request` SET " + set_clause
                  + " WHERE name=%s AND status=%s",
                  list(vals.values()) + [dsr_name, from_status])
    changed = frappe.db.sql("SELECT ROW_COUNT()")[0][0] == 1
    if changed:
        events.emit(event_type or to_status.replace(" ", ""),
                    signature_request=dsr_name, **event_kw)
    return changed


def verify_and_complete(dsr_name):
    """The governed completion path. Requires DSR already 'Signed' (verified). Sets the
    in-process call marker, then lets the ENGINE complete the level; the engine-side
    guard re-validates the persisted DSR under lock (frappe.flags is never trusted
    alone). On engine refusal (state drift) -> Manual Review ONLY if this attempt
    still owns the Signed state (R2: losers of a completion race exit as idempotent
    no-ops; terminal states are never downgraded)."""
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    dsr = frappe.db.get_value(DSR, dsr_name,
                              ["name", "status", "approval_request", "approver", "package"],
                              as_dict=True)
    if not dsr or dsr.status != "Signed":
        return {"completed": False, "reason": "not_in_signed_state"}
    prev = getattr(frappe.flags, guard.FLAG_KEY, None)
    setattr(frappe.flags, guard.FLAG_KEY, dsr.name)
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    # ATOMICITY (verification-gate correction, 2026-07-12): savepoint before the
    # engine call. If engine.approve() fails AFTER partial mutations (e.g. approver
    # row set but level activation failed), the except path FIRST rolls back to the
    # savepoint so no partial approval state can ever commit alongside the Manual
    # Review marker. Happy path stays one atomic transaction: DSR lock -> guard DB
    # validation -> engine.approve -> DSR 'Approval Completed', no intermediate commit.
    frappe.db.savepoint("esign_verify_complete")
    try:
        from ecentric_workspace.approval_center.engine import service as engine
        engine.approve(dsr.approval_request, actor=dsr.approver,
                       comment=_("Duyệt & Ký (ký số đã xác minh: {0})").format(dsr.name))
    except Exception as e:
        # R2 (2026-07-12): rollback the savepoint FIRST, then let the CURRENT
        # persisted DB state decide. Manual Review is stamped only when this
        # failing attempt still owns the eligible 'Signed' processing state
        # (conditional UPDATE); a worker that merely lost a valid concurrency
        # race exits as an idempotent no-op with NO failure/manual-review event,
        # and a terminal result (Approval Completed) is never downgraded.
        frappe.db.rollback(save_point="esign_verify_complete")
        if _guarded_dsr_transition(dsr_name, "Signed", "Manual Review",
                                   extra={"manual_review_reason": safe_error(e)[:200]},
                                   event_type="ManualReview", error_summary=safe_error(e)):
            return {"completed": False, "reason": "engine_refused", "detail": safe_error(e)}
        return {"completed": False, "reason": "already_finalized_by_parallel_worker"}
    finally:
        setattr(frappe.flags, guard.FLAG_KEY, prev)
        frappe.flags.mute_messages = prev_mute
        frappe.local.message_log = []
    # Winner finalization - also state-guarded. If a racing loser stamped
    # Manual Review in the window after our engine.approve, repair it to the true
    # terminal outcome (the engine DID approve exactly once in this transaction).
    if _guarded_dsr_transition(dsr_name, "Signed", "Approval Completed",
                               extra={"completed_at": now_datetime()},
                               event_type="ApprovalCompleted", erp_actor=dsr.approver):
        return {"completed": True}
    if _guarded_dsr_transition(dsr_name, "Manual Review", "Approval Completed",
                               extra={"completed_at": now_datetime(),
                                      "manual_review_reason": None},
                               event_type="ApprovalCompleted", erp_actor=dsr.approver):
        return {"completed": True, "note": "repaired_racer_manual_review_label"}
    # Already Approval Completed (idempotent) - nothing to do.
    return {"completed": True, "note": "already_terminal"}


# --------------------------------------------------------------------------- #
# reject / cancel / retry
# --------------------------------------------------------------------------- #
def reject_with_transition(business_doctype, business_name, comment):
    """ERP is the system of record: engine.reject FIRST (engine authorizes + requires
    reason). Provider transition is best-effort afterwards; failure never un-rejects."""
    actor = frappe.session.user
    req = _req_for_business(business_doctype, business_name)
    profile = _profile_doc(business_doctype, req.approval_type)
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        from ecentric_workspace.approval_center.engine import service as engine
        engine.reject(req.name, actor=actor, comment=comment)
    finally:
        frappe.flags.mute_messages = prev_mute
        frappe.local.message_log = []
    pkg_name = pkgsvc.active_package_for_request(req.name)
    sync_pending = 0
    if pkg_name:
        pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                                  ["scts_document_id"], as_dict=True)
        tid = _transition_id(profile.name, "Reject")
        if pkg.scts_document_id and tid is not None:
            try:
                adapter = get_adapter(_settings_for(profile))
                adapter.execute_transition(pkg.scts_document_id, tid, {"comment": comment})
                events.emit("Rejected", package=pkg_name, erp_actor=actor,
                            request_meta={"transition_id": tid})
            except Exception as e:
                sync_pending = 1
                events.emit("Failed", package=pkg_name, erp_actor=actor,
                            error_summary=safe_error(e),
                            request_meta={"phase": "reject_transition"})
    return {"rejected": True, "provider_sync_pending": sync_pending}


def cancel_signature_request(dsr_name, reason):
    """Ops action (SM): cancel a stuck signing request. Never touches approval state."""
    perms.assert_system_manager()
    if not (reason or "").strip():
        frappe.throw(_("Vui lòng nhập lý do hủy."))
    events.set_dsr_status(dsr_name, "Cancelled", event_type="Cancelled",
                          request_meta={"reason": reason})
    return {"cancelled": True}


def retry_signature_request(dsr_name):
    """Ops action (SM): re-drive from Manual Review / Retryable Failure. POLL-FIRST is
    enforced in the worker - a retry never blind-resubmits."""
    perms.assert_system_manager()
    cur = frappe.db.get_value(DSR, dsr_name, "status")
    if cur not in ("Manual Review", "Retryable Failure"):
        frappe.throw(_("Chỉ retry được yêu cầu ở trạng thái Manual Review / Retryable Failure."))
    frappe.db.set_value(DSR, dsr_name, "request_attempt",
                        (frappe.db.get_value(DSR, dsr_name, "request_attempt") or 0) + 1)
    events.set_dsr_status(dsr_name, "Queued", event_type="RetryScheduled",
                          extra_fields={"queued_at": now_datetime()})
    frappe.enqueue(
        "ecentric_workspace.approval_center.esign.tasks.process_signing_request",
        dsr_name=dsr_name, queue="default", timeout=600,
        job_name="esign_dsr_%s" % dsr_name, enqueue_after_commit=True)
    return {"queued": True}


# --------------------------------------------------------------------------- #
# status (read)
# --------------------------------------------------------------------------- #
def get_signing_status(business_doctype, business_name):
    perms.assert_can_view_business(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    out = {"enabled": False, "package": None, "requests": []}
    profile = None
    at = frappe.db.get_value(business_doctype, business_name, "approval_type") \
        if frappe.db.has_column(business_doctype, "approval_type") else None
    if not at and ar:
        at = frappe.db.get_value("EC Approval Request", ar, "approval_type")
    if at:
        profile = guard.get_active_profile(business_doctype, at)
    else:
        # draft with empty approval_type field (per-form APIs don't populate it):
        # any enabled+gated profile for this DocType decides visibility
        for r in frappe.get_all("EC Digital Signature Profile",
                                 filters={"business_doctype": business_doctype, "enabled": 1},
                                 fields=["name", "approval_type"], limit_page_length=5):
            profile = guard.get_active_profile(business_doctype, r.approval_type)
            if profile:
                break
    out["enabled"] = bool(profile)
    pkg_name = None
    if ar:
        pkg_name = pkgsvc.active_package_for_request(ar) \
            or frappe.db.get_value("EC Digital Signature Package",
                                   {"approval_request": ar}, "name")
    else:
        pkg_name = pkgsvc.draft_package_for_business(business_doctype, business_name)
    if pkg_name:
        pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                                  ["name", "status", "package_version", "package_hash",
                                   "scts_document_id", "provider", "environment",
                                   "signed_bundle_complete"], as_dict=True)
        pkg["files"] = pkgsvc.package_files(pkg_name)
        pkg["placements"] = pkgsvc.package_placements(pkg_name)
        out["package"] = pkg
    if ar:
        out["requests"] = frappe.get_all(
            DSR, filters={"approval_request": ar},
            fields=["name", "status", "action", "approver", "request_attempt",
                    "queued_at", "verified_at", "completed_at", "error_code",
                    "manual_review_reason"],
            order_by="creation asc")
    return out
