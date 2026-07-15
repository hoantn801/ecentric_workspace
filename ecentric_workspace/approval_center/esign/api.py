# Copyright (c) 2026, eCentric and contributors
"""Whitelisted esign API - thin, permission-first wrappers over the services.
No provider knowledge here. Mutations POST-only, login required (no allow_guest
anywhere). The client NEVER supplies userId / SignatureId / transitionId / hash -
everything is resolved server-side (SCTS UAT findings A-E compensating controls).

S2A note: endpoints exist for tests and for S2C/S2D UIs; no page calls them yet and
all gates default closed."""
import base64

import frappe
from frappe import _

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import service as svc
from ecentric_workspace.approval_center.esign import events


def _business_args(business_doctype, business_name):
    if not business_doctype or not business_name:
        frappe.throw(_("Thiếu tham số yêu cầu."))
    if not frappe.db.exists(business_doctype, business_name):
        frappe.throw(_("Không tìm thấy yêu cầu."))
    return business_doctype, business_name


def _file_bytes():
    """Multipart file (preferred) or base64 `filedata` fallback. Content is validated
    downstream (magic bytes / denylist / size)."""
    f = frappe.request.files.get("file") if getattr(frappe, "request", None) \
        and getattr(frappe.request, "files", None) else None
    if f:
        return f.filename, f.stream.read()
    fd = frappe.form_dict.get("filedata")
    fn = frappe.form_dict.get("filename")
    if fd and fn:
        return fn, base64.b64decode(fd)
    frappe.throw(_("Không nhận được tệp tải lên."))


# ------------------------------ package (requester) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def upload_package_file(business_doctype, business_name, requires_signature=0,
                        is_supporting_document=0, share_with_partner=0, file_kind=None):
    _business_args(business_doctype, business_name)
    perms.assert_can_view_business(business_doctype, business_name)
    at = frappe.db.get_value(business_doctype, business_name, "approval_type")
    profile = guard.get_active_profile(business_doctype, at)
    if not profile:
        frappe.throw(_("Ký số chưa được bật cho loại yêu cầu này."))
    file_name, content = _file_bytes()
    pkg = pkgsvc.get_or_create_draft(business_doctype, business_name, profile)
    row = pkgsvc.add_file(pkg.name, file_name, content,
                          requires_signature=int(requires_signature or 0),
                          is_supporting_document=int(is_supporting_document or 0),
                          share_with_partner=int(share_with_partner or 0),
                          file_kind=file_kind)
    return {"package": pkg.name, "file_row": row.name, "sha256": row.sha256}


@frappe.whitelist(methods=["POST"])
def set_file_flags(dsf_name, requires_signature=None, is_supporting_document=None,
                   share_with_partner=None, file_kind=None):
    return pkgsvc.set_file_flags(dsf_name, requires_signature, is_supporting_document,
                                 share_with_partner, file_kind)


@frappe.whitelist(methods=["POST"])
def reorder_files(package, ordered_names):
    names = frappe.parse_json(ordered_names) if isinstance(ordered_names, str) else ordered_names
    pkgsvc.reorder_files(package, names or [])
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def remove_file(dsf_name):
    pkgsvc.remove_file(dsf_name)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def save_placements(package, placements):
    rows = frappe.parse_json(placements) if isinstance(placements, str) else placements
    n = pkgsvc.save_placements(package, rows or [])
    return {"saved": n}


@frappe.whitelist()
def get_signing_status(business_doctype, business_name):
    _business_args(business_doctype, business_name)
    return svc.get_signing_status(business_doctype, business_name)


@frappe.whitelist()
def get_package_file(dsf_name):
    """Permission-checked private PDF/file streaming for the coordinate editor (S2C).
    NEVER exposes a raw /private/files URL to the client."""
    row = frappe.db.get_value("EC Digital Signature File", dsf_name,
                              ["package", "file", "file_name"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy tệp."))
    pkg = frappe.db.get_value("EC Digital Signature Package", row.package,
                              ["business_doctype", "business_name"], as_dict=True)
    perms.assert_can_view_business(pkg.business_doctype, pkg.business_name)
    fdoc = frappe.get_doc("File", row.file)
    frappe.local.response.filename = row.file_name
    frappe.local.response.filecontent = fdoc.get_content()
    frappe.local.response.type = "download"


# ------------------------------ signing (approver) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def approve_and_sign(business_doctype, business_name, comment=None):
    _business_args(business_doctype, business_name)
    return svc.approve_and_sign(business_doctype, business_name, comment=comment)


@frappe.whitelist(methods=["POST"])
def reject_and_transition(business_doctype, business_name, comment=None):
    _business_args(business_doctype, business_name)
    if not (comment or "").strip():
        frappe.throw(_("Bắt buộc nhập lý do từ chối."))
    return svc.reject_with_transition(business_doctype, business_name, comment)


# ------------------------------ ops (System Manager) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def retry_signature_request(dsr_name):
    return svc.retry_signature_request(dsr_name)


@frappe.whitelist(methods=["POST"])
def cancel_signature_request(dsr_name, reason=None):
    return svc.cancel_signature_request(dsr_name, reason)


@frappe.whitelist(methods=["POST"])
def test_connection(provider, environment):
    perms.assert_system_manager()
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": provider, "environment": environment}, "*",
                            as_dict=True)
    if not s:
        frappe.throw(_("Chưa có Provider Settings cho cặp này."))
    from ecentric_workspace.approval_center.esign.providers import get_adapter
    from ecentric_workspace.approval_center.esign.sanitize import safe_error
    from frappe.utils import now_datetime
    try:
        res = get_adapter(s).test_connection()
        out = {"ok": True, "result": res}
    except Exception as e:
        out = {"ok": False, "error": safe_error(e)}
    frappe.db.set_value("EC Digital Signature Provider Settings", s.name,
                        {"last_connection_test": now_datetime(),
                         "last_connection_result": ("OK" if out["ok"] else out["error"])[:130]})
    return out


@frappe.whitelist(methods=["POST"])
def verify_mapping(mapping_name):
    """SM-gated mapping verification: pulls provider signatures for the mapped user and
    confirms signature_id ownership. Stores SAFE metadata only (no images, no HSM)."""
    perms.assert_system_manager()
    m = frappe.get_doc("EC SCTS User Mapping", mapping_name)
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"environment": m.environment,
                             "integration_enabled": 1}, "*", as_dict=True)
    if not s:
        frappe.throw(_("Không có Provider Settings đang bật cho môi trường này."))
    from ecentric_workspace.approval_center.esign.providers import get_adapter
    from frappe.utils import now_datetime
    sigs = get_adapter(s).list_user_signatures(m.scts_user_id)
    owned = [x for x in (sigs or []) if str(x.get("id")) == str(m.signature_id)
             and str(x.get("signerId")) == str(m.scts_user_id)]
    if not owned:
        frappe.throw(_("Signature ID không thuộc user SCTS này - từ chối xác minh."))
    meta = owned[0]
    m.db_set({"mapping_status": "Verified", "verified_at": now_datetime(),
              "verified_by": frappe.session.user,
              "signature_meta_summary": ("%s / %s" % (meta.get("type") or "?",
                                                      meta.get("company") or "?"))[:130]})
    return {"verified": True}


# ------------------------------ Payment Request e2e (S2B-B) ------------------------------ #
@frappe.whitelist(methods=["POST"])
def pr_approve_and_sign(payment_request_name, comment=None):
    """Payment-Request-scoped governed Duyệt & Ký. The client supplies ONLY the PR name
    and an optional comment - never userId / signatureId / transitionId / hash. Identity,
    level, package, placements and transition are all resolved and validated server-side
    by the governed service (which runs the pre-write signer binding)."""
    _business_args("EC Payment Request", payment_request_name)
    return svc.approve_and_sign("EC Payment Request", payment_request_name, comment=comment)


@frappe.whitelist()
def pdf_page_geometry(dsf_name):
    """Page count + per-page point dimensions for governed placement entry. Permission is
    enforced against the owning package's business document; no raw file URL is exposed."""
    pkg_name = frappe.db.get_value("EC Digital Signature File", dsf_name, "package")
    if not pkg_name:
        frappe.throw(_("Không tìm thấy tệp."))
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["business_doctype", "business_name"], as_dict=True)
    perms.assert_can_view_business(pkg.business_doctype, pkg.business_name)
    return pkgsvc.pdf_page_geometry(dsf_name)


@frappe.whitelist(methods=["POST"])
def reconcile_document_creation(package, scts_document_id=None):
    """SM-gated reconciliation of an AMBIGUOUS AddDocument outcome. Either records the
    provider document id that ops found in SCTS, or clears the unknown marker to permit
    exactly one clean recreate. NEVER runs automatically; never creates a document itself."""
    perms.assert_system_manager()
    return svc.reconcile_document_creation(package, scts_document_id)


@frappe.whitelist()
def signing_readiness(payment_request_name):
    """Backend-computed Duyệt & Ký readiness for the Payment Request panel (read-only)."""
    _business_args("EC Payment Request", payment_request_name)
    return svc.signing_readiness("EC Payment Request", payment_request_name)


# ------------------------------ UAT pilot (S2B-C1) ------------------------------ #
@frappe.whitelist()
def uat_pilot_readiness(payment_request_name=None):
    """Administrator/System Manager-only READ-ONLY UAT pilot readiness checklist."""
    from ecentric_workspace.approval_center.esign import pilot
    return pilot.uat_pilot_readiness(payment_request_name)


@frappe.whitelist(methods=["POST"])
def run_scts_uat_pilot_probe(payment_request_name, apply=0):
    """Manual opt-in UAT probe. apply=0 (default) = redacted preview with NO external
    calls; apply=1 = heavily gated real UAT submit. Never runs automatically."""
    from ecentric_workspace.approval_center.esign import pilot
    return pilot.run_scts_uat_pilot_probe(payment_request_name, apply=apply)


@frappe.whitelist(methods=["POST"])
def retrieve_signed_files(payment_request_name):
    """SM-gated manual retrieval of the signed PDF(s) for a Payment Request's active
    package (safe read; idempotent; never resends AddDocument/bulk-process)."""
    perms.assert_system_manager()
    _business_args("EC Payment Request", payment_request_name)
    ar = perms.business_approval_request("EC Payment Request", payment_request_name)
    pkg = pkgsvc.active_package_for_request(ar) if ar else None
    if not pkg:
        frappe.throw(_("Không có gói tài liệu đang hoạt động."))
    from ecentric_workspace.approval_center.esign import signed_files
    return signed_files.retrieve_and_store_for_package(pkg)


# --------------------- signing UX / inbox / multi-select / review (overnight) --------------- #
@frappe.whitelist()
def signing_ui_state(business_doctype, business_name):
    """Backend-authoritative, sanitized signing state for the detail panel (read-only)."""
    _business_args(business_doctype, business_name)
    from ecentric_workspace.approval_center.esign import ui_state
    return ui_state.signing_ui_state(business_doctype, business_name)


@frappe.whitelist()
def signing_inbox(filters=None, start=0, page_length=20):
    """Permission-scoped, server-paginated Signing Inbox (governed VIEW; not an engine)."""
    from ecentric_workspace.approval_center.esign import inbox
    return inbox.signing_inbox(filters=filters, start=start, page_length=page_length)


@frappe.whitelist(methods=["POST"])
def preview_multi_select_sign(items):
    """Read-only eligibility preview for multi-select SEQUENTIAL signing - NO writes, NO
    provider calls. (Not provider bulk; SCTS multi-instance batching is deferred.)"""
    from ecentric_workspace.approval_center.esign import multi_sign
    return multi_sign.preview_multi_select(items)


@frappe.whitelist(methods=["POST"])
def multi_select_sequential_sign(items, comment=None):
    """Governed multi-select SEQUENTIAL signing across business requests. Fail-closed
    whole-selection validation; gated OFF by default; each item is signed independently
    through the verified single-item path - no provider batch call is made or implied."""
    from ecentric_workspace.approval_center.esign import multi_sign
    return multi_sign.multi_select_sequential_sign(items, comment=comment)


@frappe.whitelist()
def signed_file_reviews(package):
    """List signed-file rows awaiting hash-mismatch review (System Manager)."""
    from ecentric_workspace.approval_center.esign import review
    return review.pending_reviews(package)


@frappe.whitelist(methods=["POST"])
def resolve_signed_file_review(dsf_name, action, reason=None):
    """Resolve a signed-file hash mismatch: action in {accept, reject, keep}. SM-only,
    idempotent, immutable-audited; never overwrites the accepted file silently."""
    from ecentric_workspace.approval_center.esign import review
    if action == "accept":
        return review.accept_candidate(dsf_name, reason)
    if action == "reject":
        return review.reject_candidate(dsf_name, reason)
    if action == "keep":
        return review.keep_existing(dsf_name, reason)
    frappe.throw(_("Hành động không hợp lệ."))


@frappe.whitelist()
def placement_editor_config(payment_request_name):
    """Backend-computed EC_PPH_CONFIG for the bundled placement editor. Permission-checked;
    the client supplies ONLY the PR name and receives package/files/version/locked resolved
    server-side (never a raw private-file URL)."""
    _business_args("EC Payment Request", payment_request_name)
    perms.assert_can_view_business("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import ui_state
    st = ui_state.signing_ui_state("EC Payment Request", payment_request_name)
    pkg = st.get("package") or {}
    files = [{"name": f.get("name"), "file_name": f.get("file_name"),
              "is_pdf": f.get("is_pdf"), "requires_signature": f.get("requires_signature")}
             for f in (pkg.get("files") or [])]
    return {"package": pkg.get("name"), "files": files,
            "version": pkg.get("package_version"),
            "locked": bool(pkg.get("status") and pkg.get("status") != "Draft")}


@frappe.whitelist()
def signer_plan(payment_request_name):
    """Read-only signer plan for the Payment Request signing UI (Phase B1). Permission-safe
    (business view permission required); no writes / side effects; no SCTS call."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import signer_plan as sp
    return sp.resolve_signer_plan("EC Payment Request", payment_request_name)


@frappe.whitelist()
def requester_signing_readiness(payment_request_name):
    """Read-only requester Submit & Sign readiness (fail-closed)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import requester
    return requester.requester_signing_readiness("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_submit_and_sign(payment_request_name, comment=None):
    """Governed requester Submit & Sign. Session user must be the authoritative requester
    (no Administrator/System Manager bypass); creates/reuses one requester-scoped DSR."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import requester
    return requester.requester_submit_and_sign("EC Payment Request", payment_request_name,
                                               comment=comment)


@frappe.whitelist(methods=["POST"])
def prepare_requester_signing_package(payment_request_name):
    """Requester 'Prepare Signing Package': create/reuse the package + add eligible PDFs +
    return the editor config. No SCTS call, no DSR. Requester-only (no admin bypass)."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import requester
    return requester.prepare_requester_signing_package("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_lock_signing_package(payment_request_name):
    """Requester-local package lock (freezes hash; no SCTS). Requester-only; idempotent."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import requester
    return requester.requester_lock_signing_package("EC Payment Request", payment_request_name)


@frappe.whitelist(methods=["POST"])
def requester_reset_invalid_package(payment_request_name):
    """Governed recovery of an INVALID locked requester package (Locked/Active with zero
    requester placements). Authorized STRICTLY for the actual requester (no Administrator /
    System Manager / role bypass); audited; no provider/SCTS/DSR mutation; cancels the invalid
    local package so a fresh Draft can be prepared."""
    _business_args("EC Payment Request", payment_request_name)
    from ecentric_workspace.approval_center.esign import requester
    return requester.requester_reset_invalid_package("EC Payment Request", payment_request_name)
