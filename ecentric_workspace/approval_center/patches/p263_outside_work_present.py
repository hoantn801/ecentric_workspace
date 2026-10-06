# Copyright (c) 2026, eCentric and contributors
"""p263: ghi cong "Present" cho ngay lam viec ben ngoai DA DUYET tu 01/09/2026 (Hoan 05/10).

Truoc ban nay Outside Work duyet xong khong tao Attendance -> bang cong ERP / payroll trong
ngay do (vd bao.nguyen 24/09). Tu nay handler engine lam luc duyet xong; patch nay bu cho
phieu cu. Ngay da co ban ghi (phep, cham tay...) giu nguyen. FAIL-SAFE: nuot loi + Error Log.
"""
import frappe

TITLE = "p263 outside work present"


def execute():
    try:
        from ecentric_workspace.approval_center.features.outside_work.application import attendance
        out = attendance.backfill("2026-09-01")
        frappe.log_error(title=TITLE, message=str(out))
    except Exception:
        frappe.log_error(title=TITLE + " loi", message=frappe.get_traceback())
