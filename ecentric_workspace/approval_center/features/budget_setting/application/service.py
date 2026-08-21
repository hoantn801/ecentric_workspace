"""Business rules owned by the budget_setting module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def budget_title(doc):
    date = getdate(doc.get("period_start")) if doc.get("period_start") else None
    tag = (("%04d-%02d" % (date.year, date.month)) if doc.get("budget_period_type") == "Monthly"
           else ("%04d" % date.year)) if date else "?"
    return ("Budget Setting - %s - %s - %s" %
            (doc.get("budget_period_type") or "Annual", doc.get("department") or "?", tag))[:180]

def validate_budget(doc):
    required = ("budget_period_type", "period_start", "department", "forecast_justification",
                "has_financial_risks", "request_attachment")
    amounts = ("approved_budget_current_period", "actual_spending_current_period",
               "forecast_budget_next_period")
    if any(not str(doc.get(f) or "").strip() for f in required) or any(doc.get(f) is None for f in amounts):
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    if not frappe.db.exists("Department", doc.department): frappe.throw(_("Phòng ban không hợp lệ. Vui lòng chọn phòng ban từ danh sách."))
    if doc.budget_period_type not in ("Annual", "Monthly"): frappe.throw(_("Loại kỳ ngân sách không hợp lệ."))
    try:
        if any(float(doc.get(f)) < 0 for f in amounts): frappe.throw(_("Các giá trị ngân sách không thể là số âm."))
    except (TypeError, ValueError): frappe.throw(_("Các giá trị ngân sách phải là số."))
    date = getdate(doc.period_start)
    if doc.budget_period_type == "Annual" and (date.month != 1 or date.day != 1): frappe.throw(_("Với kỳ Năm (Annual), Ngày bắt đầu phải là ngày 1 tháng 1 (01/01)."))
    if doc.budget_period_type == "Monthly" and date.day != 1: frappe.throw(_("Với kỳ Tháng (Monthly), Ngày bắt đầu phải là ngày 1 của tháng."))
    if doc.has_financial_risks == "Yes" and not (doc.financial_risk_details or "").strip(): frappe.throw(_("Vui lòng mô tả rủi ro tài chính khi chọn 'Yes'."))

