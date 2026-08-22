"""Business rules owned by the payment_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


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
        if not (doc.purchase_request or "").strip() or not frappe.db.exists("EC Purchase Request", doc.purchase_request): frappe.throw(_("Purchase Request liên quan không hợp lệ."))
        request = frappe.db.get_value("EC Purchase Request", doc.purchase_request, "approval_request")
        if not request or frappe.db.get_value("EC Approval Request", request, "approval_status") != "Approved": frappe.throw(_("Purchase Request liên quan phải đã được duyệt (Approved/Completed) trước khi tạo Payment Request."))
    elif doc.has_purchase_request == "No" and not (doc.no_purchase_request_reason or "").strip(): frappe.throw(_("Vui lòng nhập lý do không có Purchase Request khi chọn 'No'."))

