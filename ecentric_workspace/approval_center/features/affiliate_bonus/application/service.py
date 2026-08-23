"""Business rules owned by the affiliate_bonus module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def affiliate_title(doc):
    date = getdate(doc.get("service_month")) if doc.get("service_month") else None
    month = "%04d-%02d" % (date.year, date.month) if date else "?"
    amount = doc.get("total_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Affiliate Bonus - %s - %s" % (month, amount))[:180]

def validate_affiliate(doc):
    missing = [field for field in ("service_month", "detail", "request_attachment")
               if not str(doc.get(field) or "").strip()]
    if doc.total_amount is None: missing.append("total_amount")
    if doc.budget is None: missing.append("budget")
    if missing: frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    try:
        if float(doc.total_amount) <= 0: frappe.throw(_("Tổng số tiền phải lớn hơn 0."))
        if float(doc.budget) < 0: frappe.throw(_("Ngân sách không thể là số âm."))
    except (TypeError, ValueError): frappe.throw(_("Giá trị số tiền/ngân sách không hợp lệ."))
    if getdate(doc.service_month).day != 1: frappe.throw(_("Tháng dịch vụ (Service month) phải là ngày 1 của tháng."))

