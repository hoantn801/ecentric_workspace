# Copyright (c) 2026, eCentric and contributors
"""p005_dong_bo_kiem_ke - dong bo so tai san theo file kiem ke IT + nhap ban quyen Microsoft 365 (Hoan 27/11/2026).

Doi ma EC2024 -> EC2026, nguoi giu / tra kho theo Excel (qua vong doi, co nhat ky, khong bao nguoi giu),
sua mau EC202400025 thanh man hinh S27i-30; tao 4 ban quyen M365 + cap cho theo email (khong bao).
Du lieu: tai_san/data/kiem_ke_2026_11_*.json. Idempotent. Bao cao + loi -> Error Log, khong chan migrate.
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "EC Software License"):
        return
    try:
        from ecentric_workspace.tai_san import jobs as J
        from ecentric_workspace.tai_san import sync_service as SY
        report = SY.run(J._system_ctx(), "kiem_ke_2026_11_thiet_bi.json", "kiem_ke_2026_11_m365.json")
        frappe.log_error(title="tai_san p005 bao cao (khong phai loi)",
                         message="\n".join("%s | %s | %s" % (k, a, b) for k, (a, b) in report))
    except Exception:
        frappe.log_error(title="tai_san p005_dong_bo_kiem_ke", message=frappe.get_traceback())
