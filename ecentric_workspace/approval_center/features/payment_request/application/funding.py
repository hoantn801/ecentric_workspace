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

_KOL = "ecentric_workspace.approval_center.features.contract_review.application.kol_funding."

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
    # Hop dong KOL/KOC (11/11/2026, plan "Hop dong KOL/KOC len ERP"). Khac hai nguon tren o
    # cho tran chi KHONG phai mot truong: coc chi khi creator da ky, phan con lai theo BBNT
    # da hoan tat (kol_acceptance.payable_cap). Danh sach chon hien hop dong cua minh VA cung
    # phong ban (anh Hoan: "filter theo ma contract ma ban do hoac team ban do tao").
    "EC Contract Review Request": {
        "label": "Hợp đồng KOL/KOC",
        "total": "payable_amount",
        "title": "request_title",
        "payee": "creator_name",
        "approved_via": "custom",
        "total_fn": _KOL + "funding_total",
        "approved_fn": _KOL + "funding_approved",
        "owner_fn": _KOL + "funding_owner_filters",
        "explain_fn": _KOL + "funding_explain",
        # Kiem LAI quyen dung hop dong luc nop (danh sach chon da loc team, nhung API nhan thang
        # ten hop dong) va KHOA dong hop dong khi tinh phan con lai: hai DNTT nop cung luc khong
        # cung lot qua tran (QC 11/11).
        "access_fn": _KOL + "funding_can_use",
        "lock_source": True,
        # SO doanh thu chon tren DNTT (anh Hoan 12/11) - tim SO + kiem luc nop thuoc hop dong.
        "so_fn": _KOL + "funding_so_search",
        "validate_fn": _KOL + "funding_validate",
        "so_info_fn": _KOL + "funding_so_info",
        "extra_filters": {"contract_type": "KOL/KOC / Creator (EC)"},
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
    if meta["approved_via"] == "custom":
        return bool(frappe.get_attr(meta["approved_fn"])(row.get("name")))
    if meta["approved_via"] == "approval_request":
        req = row.get("approval_request")
        if not req:
            return False
        return frappe.db.get_value("EC Approval Request", req, "approval_status") == "Approved"
    state = (row.get("workflow_state") or "").strip()
    return state in meta.get("approved_states", ())


def consumed_amount(source_doctype, source_name, exclude_request=None, for_update=False):
    """Sum of Payment Requests charged against this commitment.

    `exclude_request` leaves out the request being edited, so re-saving a draft does not
    count itself twice. Permission-free on purpose: the total must be correct regardless of
    who is looking (a user may not see somebody else's request but it still spends budget).
    """
    if not (source_doctype and source_name):
        return 0.0
    filters = {"funding_source_doctype": source_doctype, "funding_source_name": source_name}
    total = 0.0
    # for_update: doc KHOA (doc ban moi nhat da commit). Doc thuong trong REPEATABLE READ dung
    # anh chup tu dau giao dich -> khong thay DNTT vua nop cung luc, khoa dong nguon la vo ich.
    kw = {"for_update": True} if for_update else {}
    for row in frappe.get_all("EC Payment Request", filters=filters,
                              fields=["name", "payment_amount", "approval_request"],
                              ignore_permissions=True, limit_page_length=0, **kw):
        if exclude_request and row.name == exclude_request:
            continue
        status = row.approval_request and frappe.db.get_value(
            "EC Approval Request", row.approval_request, "approval_status", **kw)
        if status in CONSUMING_STATUSES:
            total += float(row.payment_amount or 0)
    return total


def source_total(source_doctype, source_name):
    meta = _meta(source_doctype)
    if meta.get("total_fn"):
        return float(frappe.get_attr(meta["total_fn"])(source_name) or 0)
    value = frappe.db.get_value(source_doctype, source_name, meta["total"])
    return float(value or 0)


def remaining_for_source(source_doctype, source_name, exclude_request=None, for_update=False):
    """committed - already charged. Never negative in the UI sense; callers compare against it."""
    return source_total(source_doctype, source_name) - consumed_amount(
        source_doctype, source_name, exclude_request, for_update=for_update)


def describe_source(source_doctype, source_name, exclude_request=None):
    """Numbers the form shows under the amount field: total / paid / remaining."""
    total = source_total(source_doctype, source_name)
    used = consumed_amount(source_doctype, source_name, exclude_request)
    return {"source_doctype": source_doctype, "source_name": source_name,
            "total": total, "used": used, "remaining": total - used}


def search_revenue_so(source_doctype, query=None, exclude_request=None, user=None):
    """SO doanh thu cho nguon co khai `so_fn` (hop dong KOL). Nguon khac: khong co o SO.
    Nguon tra danh sach SO; "da de nghi chi" tren tung SO thi tinh o day (DNTT la cua module nay)."""
    meta = _SOURCES.get(source_doctype) or {}
    if not meta.get("so_fn"):
        return {"rows": [], "missing": []}
    out = frappe.get_attr(meta["so_fn"])(user or frappe.session.user, query)
    rows = out.get("rows") or []
    spent = so_spent([r["value"] for r in rows], exclude_request)
    for r in rows:
        r["spent"] = spent.get(r["value"], 0.0)
    return {"rows": rows, "missing": out.get("missing") or []}


def so_check(doc):
    """Doi chieu SO doanh thu cua MOT DNTT cho nguoi duyet / Ke toan (trang chi tiet): doanh thu
    EC, da de nghi chi tren SO (khong tinh DNTT nay) va phan vuot. None = nguon khong co SO."""
    meta = _SOURCES.get(doc.get("funding_source_doctype") or "") or {}
    so = (doc.get("ec_sales_order") or "").strip()
    if not (meta.get("so_info_fn") and so):
        return None
    info = frappe.get_attr(meta["so_info_fn"])(so)
    if not info:
        return {"value": so, "label": so, "missing": True}
    others = so_spent([so], doc.get("name")).get(so, 0.0)
    after = others + float(doc.get("payment_amount") or 0)
    revenue = float(info.get("revenue") or 0)
    return dict(info, value=so, spent=others, after=after,
                over=(after - revenue) if revenue > 0 else 0.0)


def so_spent(names, exclude_request=None):
    """Tong DNTT dang chay / da duyet gan vao tung SO (doi chieu chi phi voi doanh thu SO)."""
    if not names:
        return {}
    rows = frappe.get_all("EC Payment Request", filters={"ec_sales_order": ["in", list(names)]},
                          fields=["name", "ec_sales_order", "payment_amount", "approval_request"],
                          ignore_permissions=True, limit_page_length=0)
    reqs = [r.approval_request for r in rows if r.approval_request]
    status = {r.name: r.approval_status for r in frappe.get_all(
        "EC Approval Request", filters={"name": ["in", reqs]}, fields=["name", "approval_status"],
        ignore_permissions=True, limit_page_length=0)} if reqs else {}
    out = {}
    for r in rows:
        if r.name == exclude_request or status.get(r.approval_request) not in CONSUMING_STATUSES:
            continue
        out[r.ec_sales_order] = out.get(r.ec_sales_order, 0.0) + float(r.payment_amount or 0)
    return out


def list_sources(source_doctype, user=None):
    """Approved commitments of `user`, each with its remaining balance, for the picker.

    Permission-aware: `frappe.get_all` runs with the caller's permissions (no ignore flag),
    so a user never sees a commitment they could not open. Only the fields the form needs
    are returned - no line items, no cost detail.
    """
    meta = _meta(source_doctype)
    user = user or frappe.session.user
    fields = ["name", meta["total"], meta["title"], meta["payee"]]
    if meta.get("owner_fn"):
        fields.append("approval_request")
        owner_filters = frappe.get_attr(meta["owner_fn"])(user)
    elif meta["approved_via"] == "approval_request":
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
        total = source_total(source_doctype, row.name) if meta.get("total_fn") else float(row.get(meta["total"]) or 0)
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
    if meta["approved_via"] != "custom":
        check_fields.append("approval_request" if meta["approved_via"] == "approval_request"
                           else "workflow_state")
    if meta.get("access_fn"):
        user = doc.get("requested_by") or frappe.session.user
        if not frappe.get_attr(meta["access_fn"])(user, source_name):
            frappe.throw(_("Bạn không dùng được chứng từ nguồn {0}: chỉ hợp đồng của bạn hoặc "
                           "cùng phòng ban.").format(source_name), frappe.PermissionError)
    if meta.get("validate_fn"):
        frappe.get_attr(meta["validate_fn"])(doc, doc.get("requested_by") or frappe.session.user)
    row = frappe.db.get_value(source_doctype, source_name, check_fields, as_dict=True,
                              for_update=bool(meta.get("lock_source")))
    if not _is_approved(source_doctype, row, meta):
        frappe.throw(_("Chứng từ nguồn {0} chưa được duyệt nên chưa thể tạo đề nghị thanh toán."
                       ).format(source_name))

    amount = float(doc.get("payment_amount") or 0)
    remaining = remaining_for_source(source_doctype, source_name, exclude_request=doc.get("name"),
                                     for_update=bool(meta.get("lock_source")))
    # Epsilon must stay BELOW the smallest real unit: VND has no subunit, so a tolerance of
    # 1 would let someone overspend by exactly one dong (caught by test_one_over_is_refused).
    # 0.5 absorbs float noise on Currency (stored decimal(21,9)) without hiding a real overspend.
    if amount > remaining + 0.5 and meta.get("explain_fn"):
        frappe.throw(frappe.get_attr(meta["explain_fn"])(source_name, amount, remaining))
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
