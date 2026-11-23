# Copyright (c) 2026, eCentric and contributors
"""p461_resync_tong_quan_tab_ky_luat (23/11/2026, Dot 3 HR - Ky luat): /tong-quan - khung ho so
nhan su them tab "Ky luat" (the vang + ho so do/den cua mot nguoi, du lieu tu
hr.ky_luat.controllers.api.employee_discipline - quyen xem kiem o server). Sua NGUON trang
(hr/pages/tong_quan/main_section.html) roi sync lai (A65). Tu bat loi, khong nem."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.hr.pages.tong_quan import page_sync as tong_quan
        res = tong_quan.sync() or {}
        frappe.logger("approval_center").info("p461 tong-quan: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p461: tong-quan refused (live drift): %s" % res, "p461_resync_tong_quan_tab_ky_luat")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p461_resync_tong_quan_tab_ky_luat failed")
