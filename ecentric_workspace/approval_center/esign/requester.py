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
DSF = "EC Digital Signature File"  # canonical package-file DocType (as in signed_files/pilot/review)
# request may (re)start requester signing from these states (retry-safe).
_START_STATES = ("Pending", "Reconciliation Required", "Failed")
# a DSR that still holds/represents a live or completed provider job.
_LIVE_OR_DONE = ("Draft", "Prepared", "Queued", "Provider Accepted", "Verifying",
                 "Signed", "Approval Completed")


def _profile_and_settings(business_doctype, approval_type):
    pname = guard.get_enabled_profile(business_doctype, approval_type)
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
    # execution gates (fail-closed for the ACTION; deferral already happened at submit).
    checks["gates_enabled"] = bool(st and st.get("integration_enabled")
                                   and st.get("allow_document_creation")
                                   and st.get("allow_signing"))
    pkg_name = pkgsvc.active_package_for_request(ar)
    pkg = frappe.db.get_value(PKG, pkg_name, ["status", "package_hash"], as_dict=True) if pkg_name else None
    checks["package_active_hash_valid"] = bool(
        pkg and pkg.status == "Active" and pkg.package_hash
        and pkgsvc.compute_hash(pkg_name) == pkg.package_hash)
    checks["placements_complete"] = bool(pkg_name and not pkgsvc.preflight_for_lock(pkg_name))
    # --- ADDITIVE (requester panel state mapping only) ---------------------------------
    # The requester package follows a LOCAL lifecycle (Draft -> Locked) while the write
    # gates are OFF; it never reaches "Active" (only the provider worker sets "Active",
    # which needs Signing ON). The Active-scoped keys above are left byte-identical so
    # `ready`/`reasons` are unchanged; the keys below let the requester UI represent the
    # four local states (no package / placement incomplete / ready to lock / locked)
    # WITHOUT coupling to the gates. Resolve the current requester package for this
    # business doc across statuses (the draft carries business_doctype/business_name and
    # lock_package preserves them), newest non-terminal first.
    cur_name = pkgsvc.active_package_for_request(ar) or frappe.db.get_value(
        PKG, {"business_doctype": business_doctype, "business_name": business_name,
              "status": ["not in", ("Cancelled", "Superseded", "Completed")]},
        "name", order_by="creation desc")
    cur = frappe.db.get_value(PKG, cur_name, ["status", "package_hash"],
                              as_dict=True) if cur_name else None
    checks["package_present"] = bool(cur)
    checks["package_locked"] = bool(
        cur and cur.status in ("Locked", "Active") and cur.package_hash)
    checks["placements_ready"] = bool(
        cur_name and cur and cur.status == "Draft"
        and not pkgsvc.preflight_for_lock(cur_name))
    required = ["signing_enabled", "requester_signature_required", "is_requester",
                "pending_requester_signature", "verified_mapping", "provider_uat",
                "gates_enabled", "package_active_hash_valid", "placements_complete"]
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
    # Execution gates are fail-closed here: with Integration / Document Creation / Signing OFF
    # NO SCTS write is made and no requester DSR is created - the request stays Pending
    # Requester Signature and Level 1 stays inactive.
    if not (st.get("integration_enabled") and st.get("allow_document_creation")
            and st.get("allow_signing")):
        frappe.throw(_("Cổng ký số chưa được bật (Integration / Tạo tài liệu / Ký). "
                       "Không thể Gửi & Ký cho tới khi quản trị bật các cổng này."),
                     frappe.PermissionError)
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


def _add_requester_pdf_files(pkg_name, business_doctype, business_name):
    """Add the business document's ELIGIBLE private PDF attachments to the package as signable
    files (idempotent by SHA-256). Non-PDF / non-private / invalid content is skipped or fails
    closed inside package.add_file's validation. Never touches SCTS."""
    from ecentric_workspace.approval_center.esign import hashing
    have_sha = set()
    for row in frappe.get_all(DSF, filters={"package": pkg_name}, fields=["sha256"]):
        if row.sha256:
            have_sha.add(row.sha256)
    seen_url = set()
    added = 0
    # is_private=1 + attached_to_doctype/name keeps this to PDFs directly linked to THIS
    # Payment Request; attached_to_field is intentionally NOT filtered, so both the
    # request_attachment field-attachment and its null-field twin qualify.
    for f in frappe.get_all("File",
                            filters={"attached_to_doctype": business_doctype,
                                     "attached_to_name": business_name, "is_private": 1},
                            fields=["name", "file_name", "file_url"]):
        # PDF eligibility from canonical File metadata (file_name OR file_url) - never a
        # browser-supplied MIME, which may be absent. add_file re-checks PDF magic bytes.
        name_l = (f.file_name or "").lower()
        url_l = (f.file_url or "").lower()
        if not (name_l.endswith(".pdf") or url_l.endswith(".pdf")):
            continue
        # de-dupe multiple File rows for the SAME physical PDF by canonical URL first (cheap),
        # then by content SHA - so the same file is added exactly once per package.
        if f.file_url and f.file_url in seen_url:
            continue
        content = frappe.get_doc("File", f.name).get_content()
        sha = hashing.sha256_bytes(content)
        if sha in have_sha:
            if f.file_url:
                seen_url.add(f.file_url)
            continue
        display_name = f.file_name or (f.file_url or "").rsplit("/", 1)[-1] or "document.pdf"
        pkgsvc.add_file(pkg_name, display_name, content, requires_signature=1)
        have_sha.add(sha)          # update in-loop: identical twins are added once
        if f.file_url:
            seen_url.add(f.file_url)
        added += 1
    return added


def prepare_requester_signing_package(business_doctype, business_name):
    """Governed 'Prepare Signing Package' for a requester in pre-approval. Session user must be
    the authoritative requester (NO admin/SM bypass); creates OR reuses exactly one internal
    package (idempotent), adds eligible private PDFs, and returns the placement-editor config.
    Makes NO SCTS call and creates NO DSR/provider document (gates may be OFF)."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name) \
        or _requester_ar(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Không tìm thấy yêu cầu duyệt cho phiếu này."))
    req = frappe.db.get_value(AR, ar, ["approval_type", "reference_doctype", "requested_by",
                                       "requester_signature_status", "current_level"], as_dict=True)
    if actor != req.requested_by:
        frappe.throw(_("Chỉ người đề nghị mới được chuẩn bị gói ký."), frappe.PermissionError)
    if req.requester_signature_status not in _START_STATES + ("Processing",):
        frappe.throw(_("Yêu cầu không ở giai đoạn chờ người đề nghị ký."))
    pname = guard.get_enabled_profile(req.reference_doctype, req.approval_type)
    if not pname or not guard.requester_signature_required(req.reference_doctype, req.approval_type):
        frappe.throw(_("Loại yêu cầu này không yêu cầu chữ ký của người đề nghị."))
    mapping = perms.verified_mapping(req.requested_by,
                                     frappe.db.get_value("EC Digital Signature Profile", pname,
                                                         "environment"))
    if not mapping:
        frappe.throw(_("Người đề nghị chưa có ánh xạ chữ ký SCTS được xác minh."))
    frappe.db.get_value(AR, ar, "name", for_update=True)  # idempotency lock
    pkg = pkgsvc.get_or_create_draft(business_doctype, business_name, pname, allow_submitted=True)
    if pkg.status == "Draft":
        _add_requester_pdf_files(pkg.name, business_doctype, business_name)
    # Build the editor config directly from THIS package. ui_state/get_signing_status resolve
    # a package by Active status or approval_request link, and an unlocked requester Draft has
    # NEITHER (approval_request is set only at lock), so routing through it would report zero
    # files here even though the Draft holds them.
    files = [{"name": r.name, "file_name": r.file_name, "is_pdf": r.is_pdf,
              "requires_signature": r.requires_signature}
             for r in pkgsvc.package_files(pkg.name)]
    return {"package": pkg.name, "status": pkg.status,
            "config": {"package": pkg.name, "files": files,
                       "version": pkg.package_version,
                       "locked": bool(pkg.status != "Draft")}}


def requester_lock_signing_package(business_doctype, business_name):
    """Lock the requester's package locally (freezes the hash) after placements are set - no
    SCTS call. Requester-only; idempotent (a Locked/Active package is returned as-is)."""
    actor = frappe.session.user
    ar = perms.business_approval_request(business_doctype, business_name) \
        or _requester_ar(business_doctype, business_name)
    req = frappe.db.get_value(AR, ar, ["requested_by"], as_dict=True) if ar else None
    if not req or actor != req.requested_by:
        frappe.throw(_("Chỉ người đề nghị mới được khóa gói ký."), frappe.PermissionError)
    pkg_name = pkgsvc.draft_package_for_business(business_doctype, business_name) \
        or pkgsvc.active_package_for_request(ar)
    if not pkg_name:
        frappe.throw(_("Chưa có gói tài liệu để khóa."))
    status = frappe.db.get_value(PKG, pkg_name, "status")
    if status in ("Locked", "Active"):
        return {"package": pkg_name, "status": status, "locked": True, "duplicate": True}
    h = pkgsvc.lock_package(pkg_name, ar)
    return {"package": pkg_name, "status": "Locked", "package_hash": h, "locked": True}


def _requester_ar(business_doctype, business_name):
    """Resolve the active Approval Request by its OWN reference fields (authoritative)."""
    rows = frappe.get_all(AR, filters={"reference_doctype": business_doctype,
                                       "reference_name": business_name},
                          fields=["name", "approval_status"], order_by="creation desc",
                          limit_page_length=20)
    return next((r.name for r in rows if r.approval_status == "Pending"),
                (rows[0].name if rows else None))
