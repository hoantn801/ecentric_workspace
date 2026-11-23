# Copyright (c) 2026, eCentric and contributors
"""p492_xep_tai_chinh_len_dau (23/11/2026, Hoan: "nen xep tai chinh & ngan sach o tren, tan suat moi
nguoi dung nhieu"): dua danh muc FINANCE_BUDGET len TRUOC Human Resources tren Approval Center.

Chi doi sort_order cua MOT danh muc (khong xoa, khong doi ten). Da dung truoc HR roi thi bo qua.
Ket qua ghi Error Log "p492 ...". Khong nem loi."""
import frappe

CAT = "FINANCE_BUDGET"
HR = "HR"


def execute():
    try:
        if not frappe.db.exists("EC Approval Category", CAT):
            return
        fin = frappe.db.get_value("EC Approval Category", CAT, "sort_order") or 0
        hr = frappe.db.get_value("EC Approval Category", HR, "sort_order") if frappe.db.exists(
            "EC Approval Category", HR) else None
        if hr is None or fin < hr:
            frappe.log_error(title="p492 xep tai chinh", message="bo qua: FIN=%s HR=%s" % (fin, hr))
            return
        new = max(int(hr) - 5, 0)
        frappe.db.set_value("EC Approval Category", CAT, "sort_order", new)
        frappe.db.commit()
        frappe.log_error(title="p492 xep tai chinh", message="FINANCE_BUDGET sort_order %s -> %s (HR=%s)"
                         % (fin, new, hr))
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p492_xep_tai_chinh_len_dau failed")
