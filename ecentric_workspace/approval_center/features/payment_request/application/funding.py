# Copyright (c) 2026, eCentric and contributors
"""Funding source ("nguon chi phi") for a Payment Request.

ONE place that answers "how much of this commitment is still unpaid", used by BOTH the
picker (autofill) and the submit-time guard. Two formulas that must agree would drift, so
there is only one: `remaining_for_source`.

Design notes
------------
* **Config-driven, not hardcoded per type.** `_SOURCES` describes how to read each kind of
  commitment. Adding a new one (AI Topup, bonuses...) is one dict entry - no branching in
  the callers, no schema change: the link is a Dynamic Link pair on EC Payment Request.
* **Nothing is stored on the source document.** "Already paid" is COMPUTED from the Payment
  Requests pointing at it. A stored status would be a second source of truth that silently
  drifts whenever a request is rejected, cancelled or edited. Computing cannot drift, and a
  rejected request releases its amount automatically.
* **Permission-aware.** The picker only returns commitments the current user may read;
  `frappe.get_all` is called WITHOUT ignore_permissions so existing rules apply as-is.
* Approved AND in-flight requests both consume budget - otherwise two pending requests could
  each pass the guard and together overspend.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.requests.capabilities import OPEN_STATUSES

#: A Payment Request consumes its source's budget while it is in-flight or approved.
#: Rejected/Cancelled release it; a Draft (no approval request yet) has not committed.
CONSUMING_STATUSES = tuple(OPEN_STATUSES) + ("Approved",)

#: Registry of supported commitment types. `total` is the field holding the committed amount.
#: `approved_via` says how to tell the commitment itself is approved:
#:   "approval_request" -> Approval Center engine (EC * Request doctypes)
#:   "workflow_state"   -> Frappe native workflow (Purchase Order), value in `approved_states`
_SOURCES = {
    "EC Purchase Request": {
        "label": "Đề nghị mua hàng (ĐNMH)",
        "total": "payment_amount",
        "title": "request_title",
        "payee": "supplier_name",
        "approved_via": "approval_request",
        "extra_filters": {},
    },
    "Purchase Order": {
        "label": "PO mua ngoài (sổ EC)",
        "total": "grand_total",
        "title": "title",
        "payee": "supplier",
        "approved_via": "workflow_state",
        "approved_states": ("Approved", "Completed", "Approved by CEO"),
        # Only the eCentric book. The Boxme flow uses its own doctype, never this one.
        "extra_filters": {"company": "eCentric", "docstatus": ["<", 2]},
    },
}


def supported_sources():
    """[{value, label}] for the source-type picker. Config-driven, order is stable."""
    return [{"value": dt, "label": meta["label"]} for dt, meta in _SOURCES.items()]


def _meta(source_doctype):
    meta = _SOURCES.get(source_doctype)
    if not meta:
        frappe.throw(_("Loại nguồn chi phí không hợp lệ: {0}").format(source_doctype))
    return meta


def _is_approved(source_doctype, row, meta):
    """True when the commitment itself has cleared its own approval chain. Fail-closed."""
    if meta["approved_via"] == "approval_request":
        req = row.get("approval_request")
        if not req:
            return False
        return frappe.db.get_value("EC Approval Request", req, "approval_status") == "Approved"
    state = (row.get("workflow_state") or "").strip()
    return state in meta.get("approved_states", ())


def consumed_amount(source_doctype, source_name, exclude_request=None):
    """Sum of Payment Requests charged against this commitment.

    `exclude_request` leaves out the request being edited, so re-saving a draft does not
    count itself twice. Permission-free on purpose: the total must be correct regardless of
    who is looking (a user may not see somebody else's request but it still spends budget).
    """
    if not (source_doctype and source_name):
        return 0.0
    filters = {"funding_source_doctype": source_doctype, "funding_source_name": source_name}
    total = 0.0
    for row in frappe.get_all("EC Payment Request", filters=filters,
                              fields=["name", "payment_amount", "approval_request"],
                              ignore_permissions=True, limit_page_length=0):
        if exclude_request and row.name == exclude_request:
            continue
        status = row.approval_request and frappe.db.get_value(
            "EC Approval Request", row.approval_request, "approval_status")
        if status in CONSUMING_STATUSES:
            total += float(row.payment_amount or 0)
    return total


def source_total(source_doctype, source_name):
    meta = _meta(source_doctype)
    value = frappe.db.get_value(source_doctype, source_name, meta["total"])
    return float(value or 0)


def remaining_for_source(source_doctype, source_name, exclude_request=None):
    """committed - already charged. Never negative in the UI sense; callers compare against it."""
    return source_total(source_doctype, source_name) - consumed_amount(
        source_doctype, source_name, exclude_request)


def describe_source(source_doctype, source_name, exclude_request=None):
    """Numbers the form shows under the amount field: total / paid / remaining."""
    total = source_total(source_doctype, source_name)
    used = consumed_amount(source_doctype, source_name, exclude_request)
    return {"source_doctype": source_doctype, "source_name": source_name,
            "total": total, "used": used, "remaining": total - used}


def list_sources(source_doctype, user=None):
    """Approved commitments of `user`, each with its remaining balance, for the picker.

    Permission-aware: `frappe.get_all` runs with the caller's permissions (no ignore flag),
    so a user never sees a commitment they could not open. Only the fields the form needs
    are returned - no line items, no cost detail.
    """
    meta = _meta(source_doctype)
    user = user or frappe.session.user
    fields = ["name", meta["total"], meta["title"], meta["payee"]]
    if meta["approved_via"] == "approval_request":
        fields.append("approval_request")
        owner_filters = {"requested_by": user}
    else:
        fields.append("workflow_state")
        owner_filters = {"owner": user}
    filters = dict(meta.get("extra_filters") or {})
    filters.update(owner_filters)

    rows = frappe.get_all(source_doctype, filters=filters, fields=list(dict.fromkeys(fields)),
                          order_by="modified desc", limit_page_length=200)
    out = []
    for row in rows:
        if not _is_approved(source_doctype, row, meta):
            continue
        total = float(row.get(meta["total"]) or 0)
        used = consumed_amount(source_doctype, row.name)
        remaining = total - used
        title = row.get(meta["title"]) or row.name
        out.append({
            "value": row.name,
            "label": "%s — %s" % (row.name, title),
            "title": title,
            "payee": row.get(meta["payee"]) or "",
            "total": total, "used": used, "remaining": remaining,
        })
    return out


def validate_funding(doc):
    """Submit-time guard. Called from validate_payment; same maths as the picker.

    Fails closed: an unknown or unapproved source is refused rather than silently allowed.
    """
    source_doctype = (doc.get("funding_source_doctype") or "").strip()
    source_name = (doc.get("funding_source_name") or "").strip()
    if not source_doctype and not source_name:
        return
    if not (source_doctype and source_name):
        frappe.throw(_("Vui lòng chọn đầy đủ loại nguồn chi phí và chứng từ nguồn."))
    meta = _meta(source_doctype)
    if not frappe.db.exists(source_doctype, source_name):
        frappe.throw(_("Chứng từ nguồn không tồn tại: {0} {1}").format(source_doctype, source_name))

    check_fields = ["name"]
    check_fields.append("approval_request" if meta["approved_via"] == "approval_request"
                       else "workflow_state")
    row = frappe.db.get_value(source_doctype, source_name, check_fields, as_dict=True)
    if not _is_approved(source_doctype, row, meta):
        frappe.throw(_("Chứng từ nguồn {0} chưa được duyệt nên chưa thể tạo đề nghị thanh toán."
                       ).format(source_name))

    amount = float(doc.get("payment_amount") or 0)
    remaining = remaining_for_source(source_doctype, source_name, exclude_request=doc.get("name"))
    # Epsilon must stay BELOW the smallest real unit: VND has no subunit, so a tolerance of
    # 1 would let someone overspend by exactly one dong (caught by test_one_over_is_refused).
    # 0.5 absorbs float noise on Currency (stored decimal(21,9)) without hiding a real overspend.
    if amount > remaining + 0.5:
        frappe.throw(_(
            "Số tiền {0} vượt quá phần còn lại của {1}. Tổng: {2} — đã thanh toán: {3} — còn lại: {4}."
        ).format(_fmt(amount), source_name,
                 _fmt(source_total(source_doctype, source_name)),
                 _fmt(consumed_amount(source_doctype, source_name, exclude_request=doc.get("name"))),
                 _fmt(remaining)))


def _fmt(value):
    try:
        return "{:,.0f}".format(float(value or 0)).replace(",", ".")
    except (TypeError, ValueError):
        return str(value)
