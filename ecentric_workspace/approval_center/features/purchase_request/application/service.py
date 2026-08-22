"""Business rules owned by the purchase_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def purchase_title(doc):
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Purchase Request - %s - %s" % (doc.get("department") or "?", amount))[:180]

def validate_purchase(doc):
    required = ("department", "justification", "purchase_details", "payment_term", "supplier_type",
                "supplier_name", "additional_notes_comments", "estimated_purchase_date",
                "estimated_delivery_date", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    if not frappe.db.exists("Department", doc.department): frappe.throw(_("Phòng ban không hợp lệ. Vui lòng chọn phòng ban từ danh sách."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("Số tiền thanh toán phải lớn hơn 0."))
    except (TypeError, ValueError): frappe.throw(_("Số tiền thanh toán phải là số."))
    if doc.payment_term == "Other" and not (doc.payment_term_other or "").strip(): frappe.throw(_("Vui lòng nhập điều khoản thanh toán khác khi chọn 'Other'."))
    if doc.estimated_delivery_date < doc.estimated_purchase_date: frappe.throw(_("Ngày giao hàng dự kiến không thể trước ngày mua dự kiến."))

