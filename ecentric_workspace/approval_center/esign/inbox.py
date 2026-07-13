# Copyright (c) 2026, eCentric and contributors
"""Governed Signing Inbox (Phase 3).

This is NOT a second approval engine - it is a permission-scoped VIEW over the existing
Approval Engine (EC Approval Request + Approver rows), the esign package/DSR, and provider
state. Scope is enforced server-side: a non-System-Manager sees ONLY requests where they
hold a Pending approver row at the request's current, signature-required level. A System
Manager may see all in-scope items and may narrow by company/department. List counts and
rows use the SAME governed scope, so nothing leaks across departments/brands/companies.
No raw PDF bytes are ever loaded in list views; pagination is server-side.
"""
import frappe
from frappe.utils import getdate

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import ui_state

AR = "EC Approval Request"
APPROVER = "EC Approval Request Approver"
DSR = "EC Digital Signature Request"

_CANDIDATE_CAP = 1000  # hard bound on the scoped candidate set derived per request

# derived provider-state buckets
BUCKETS = ("my_pending", "ready_to_sign", "package_incomplete", "awaiting_provider",
           "verification_pending", "signed_file_pending", "manual_review", "completed")


def _scoped_candidate_ars(filters, user, is_sm):
    """Permission-scoped candidate AR set with coarse filters pushed into the DATABASE
    (scope, status, approval_type, department, date range). Returns (rows, exact_scope_count)
    where exact_scope_count is a DB COUNT over the full governed scope (not the capped page).
    A non-SM is scoped to their own Pending approver rows; an SM may filter by department."""
    f = filters or {}
    want_completed = f.get("bucket") == "completed"
    conds = [["approval_status", "=", "Approved" if want_completed else "Pending"]]
    if f.get("approval_type"):
        conds.append(["approval_type", "=", f["approval_type"]])
    if is_sm and f.get("requester_department"):
        conds.append(["requester_department", "=", f["requester_department"]])
    if f.get("from_date"):
        conds.append(["submitted_at", ">=", getdate(f["from_date"])])
    if f.get("to_date"):
        conds.append(["submitted_at", "<=", getdate(f["to_date"])])
    if not is_sm or f.get("mine_only"):
        rows = frappe.get_all(APPROVER, filters={"approver": user, "status": "Pending"},
                              fields=["approval_request"], limit_page_length=0)
        ar_names = sorted({r.approval_request for r in rows})
        if not ar_names:
            return [], 0
        conds.append(["name", "in", ar_names])
    # exact full-scope count (DB), then a capped page-ordered slice for per-row derivation
    scope_count = _count(conds)
    ars = frappe.get_all(AR, filters=conds,
                         fields=["name", "reference_doctype", "reference_name",
                                 "requested_by", "requester_department", "approval_type",
                                 "approval_status", "current_level", "submitted_at",
                                 "completed_at"],
                         order_by="submitted_at desc", limit_page_length=_CANDIDATE_CAP)
    return ars, scope_count


def _count(conds):
    """Exact COUNT(*) over the governed scope using the same coarse conditions."""
    return frappe.db.count(AR, filters=conds)


def _amount(doctype, name):
    """Safe amount/currency when the business doctype exposes them; else (None, None)."""
    amount = cur = None
    try:
        if frappe.db.has_column(doctype, "payment_amount"):
            amount = frappe.db.get_value(doctype, name, "payment_amount")
        for c in ("currency", "transaction_currency"):
            if frappe.db.has_column(doctype, c):
                cur = frappe.db.get_value(doctype, name, c)
                break
    except Exception:
        pass
    return amount, cur


def _derive_row(ar, user, is_sm):
    """Compute the governed inbox row for a candidate AR. Returns None if the current level
    is not signature-required (only signable work belongs in this inbox)."""
    if not ar.reference_doctype or not ar.reference_name:
        return None
    sig_level = bool(ar.current_level and guard.level_requires_signature(
        ar.reference_doctype, ar.approval_type, ar.current_level)) \
        if ar.approval_status == "Pending" else False
    completed = ar.approval_status == "Approved"
    if not sig_level and not completed:
        return None
    # is THIS user the active approver? (non-SM rows are already scoped to this)
    is_active = bool(ar.approval_status == "Pending" and ar.current_level
                     and perms.pending_approver_row(ar.name, ar.current_level, user))
    pkg_name = pkgsvc.active_package_for_request(ar.name)
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "status", "package_version", "package_hash",
                               "scts_document_id", "signed_bundle_complete"],
                              as_dict=True) if pkg_name else None
    dsr = ui_state._primary_dsr(ar.name)
    signed_complete = bool(pkg and pkg.signed_bundle_complete)
    stage = ui_state._stage(pkg, dsr, signed_complete)
    bucket = _bucket_for(ar, pkg, dsr, stage, is_active)
    file_count = frappe.db.count("EC Digital Signature File", {"package": pkg_name}) \
        if pkg_name else 0
    amount, cur = _amount(ar.reference_doctype, ar.reference_name)
    safe_error = ui_state._SAFE_ERROR.get(dsr.error_code) if (dsr and dsr.error_code) else None
    return {
        "approval_request": ar.name, "business_doctype": ar.reference_doctype,
        "business_name": ar.reference_name, "requester": ar.requested_by,
        "requester_department": ar.requester_department,
        "approval_type": ar.approval_type, "amount": amount, "currency": cur,
        "active_level": ar.current_level, "is_active_approver": is_active,
        "submitted_at": str(ar.submitted_at or ""), "stage": stage, "bucket": bucket,
        "package": pkg.name if pkg else None,
        "package_status": pkg.status if pkg else None,
        "package_ready": bool(pkg and pkg.status == "Active" and pkg.package_hash),
        "file_count": file_count,
        "provider_document": bool(pkg and pkg.scts_document_id),
        "dsr_status": dsr.status if dsr else None,
        "signed_bundle_complete": signed_complete,
        "safe_error": safe_error,
    }


def _bucket_for(ar, pkg, dsr, stage, is_active):
    if ar.approval_status == "Approved":
        return "completed"
    if stage in ("Verification Mismatch", "Manual Review"):
        return "manual_review"
    if dsr and dsr.status in ("Verification Mismatch", "Manual Review"):
        return "manual_review"
    if stage == "Signed File Pending":
        return "signed_file_pending"
    if stage == "Verifying" or stage == "Signed":
        return "verification_pending"
    if stage in ("Creating Provider Document", "Provider Document Created",
                 "Signing Submitted"):
        return "awaiting_provider"
    if not pkg or pkg.status != "Active" or not pkg.package_hash:
        return "package_incomplete"
    return "ready_to_sign"


def signing_inbox(filters=None, start=0, page_length=20):
    """Permission-scoped, server-paginated inbox. Coarse filters are pushed into the DB and
    the full governed scope is counted exactly; derived provider-state buckets are computed
    over a capped candidate slice, so when the scope exceeds the cap the derived counts are
    flagged approximate (approximate_count=true) rather than presented as an exact total."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    user = frappe.session.user
    is_sm = perms.is_system_manager(user)
    cands, scope_count = _scoped_candidate_ars(filters, user, is_sm)
    truncated = scope_count > _CANDIDATE_CAP
    rows = []
    for ar in cands:
        r = _derive_row(ar, user, is_sm)
        if r is not None:
            rows.append(r)
    b = filters.get("bucket")
    if b and b not in ("completed",):
        if b == "my_pending":
            rows = [r for r in rows if r["is_active_approver"]]
        else:
            rows = [r for r in rows if r["bucket"] == b]
    derived_total = len(rows)
    start = int(start or 0)
    page_length = max(1, min(int(page_length or 20), 100))
    page = rows[start:start + page_length]
    counts = {k: 0 for k in BUCKETS}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
        if r["is_active_approver"]:
            counts["my_pending"] += 1
    # `scope_total` is the exact DB count of the governed scope; `total` is the derived count
    # over the examined slice. When truncated the derived figures are approximate.
    return {"rows": page, "total": derived_total, "scope_total": scope_count,
            "approximate_count": truncated, "start": start, "page_length": page_length,
            "counts": counts, "counts_approximate": truncated, "truncated": truncated,
            "candidate_cap": _CANDIDATE_CAP, "is_system_manager": is_sm}
