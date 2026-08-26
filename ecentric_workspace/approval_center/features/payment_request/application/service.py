"""Business rules owned by the payment_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate
from ecentric_workspace.approval_center.features.payment_request.application import funding


def payment_title(doc):
    """User-entered title wins; auto-generated 'Payment Request - payee - amount' only when
    the title is left blank (2026-08-23: the form now has an explicit title field, which also
    feeds eContract docTitle via the profile's title_source)."""
    manual = (doc.get("request_title") or "").strip()
    if manual:
        return manual[:180]
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Payment Request - %s - %s" % (doc.get("payee_full_name") or "?", amount))[:180]

def normalize_payment(doc):
    doc.details_and_attachments_correct = ("Yes" if doc.details_and_attachments_correct is True
        or str(doc.details_and_attachments_correct or "").strip().lower() in ("yes", "1", "true") else "No")
    _sync_funding_aliases(doc)


def _sync_funding_aliases(doc):
    """Keep the legacy `purchase_request` field and the generic funding pair in step.

    `purchase_request` predates the generic pair and is still read by older code paths and by
    historical records, so we dual-write instead of dropping it. The generic pair is canonical;
    the legacy field mirrors it only when the source IS an EC Purchase Request.
    """
    src_dt = (doc.get("funding_source_doctype") or "").strip()
    src_name = (doc.get("funding_source_name") or "").strip()
    legacy = (doc.get("purchase_request") or "").strip()
    if src_dt and src_name:
        doc.purchase_request = src_name if src_dt == "EC Purchase Request" else None
    elif legacy:
        # Older client (or historical draft) only set the legacy field -> promote it.
        doc.funding_source_doctype = "EC Purchase Request"
        doc.funding_source_name = legacy

def validate_payment(doc):
    required = ("reason", "payment_date", "payee_full_name", "account_bank", "bank_account_number",
                "has_purchase_request", "is_cost_valid", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("Số tiền thanh toán phải lớn hơn 0."))
    except (TypeError, ValueError): frappe.throw(_("Số tiền thanh toán phải là số."))
    normalize_payment(doc)
    if doc.details_and_attachments_correct != "Yes": frappe.throw(_("Vui lòng tích xác nhận thông tin và tệp đính kèm là chính xác trước khi gửi."))
    if doc.has_purchase_request == "Yes":
        if not (doc.get("funding_source_doctype") or "").strip() or not (doc.get("funding_source_name") or "").strip():
            frappe.throw(_("Vui lòng chọn chứng từ nguồn (ĐNMH hoặc PO) cho khoản thanh toán này."))
    elif doc.has_purchase_request == "No":
        if not (doc.no_purchase_request_reason or "").strip():
            frappe.throw(_("Vui lòng nhập lý do không có Purchase Request khi chọn 'No'."))
        # "No" must not smuggle a source through a stale draft value.
        doc.funding_source_doctype = None
        doc.funding_source_name = None
        doc.purchase_request = None
    # Single guard for every source type: exists + approved + does not exceed the remainder.
    funding.validate_funding(doc)

