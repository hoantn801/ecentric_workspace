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
