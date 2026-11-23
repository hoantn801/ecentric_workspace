# Copyright (c) 2026, eCentric and contributors
"""p480_resync_tong_quan_tieu_de_ky_luat (24/11/2026, Hoan chot 23/11 - tieu de the vang / ho so ky
luat): /tong-quan - tab "Ky luat" tren ho so nhan su hien TIEU DE (tieu de da nhap hoac tieu de du
phong cua ban ghi cu, do hr.ky_luat.controllers.api.employee_discipline tra). Sua NGUON trang
(hr/pages/tong_quan/main_section.html) roi sync lai (A65). Tu bat loi, khong nem, khong goi ra ngoai."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.hr.pages.tong_quan import page_sync as tong_quan
        res = tong_quan.sync() or {}
        frappe.logger("approval_center").info("p480 tong-quan: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p480: tong-quan refused (live drift): %s" % res,
                             "p480_resync_tong_quan_tieu_de_ky_luat")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p480_resync_tong_quan_tieu_de_ky_luat failed")
