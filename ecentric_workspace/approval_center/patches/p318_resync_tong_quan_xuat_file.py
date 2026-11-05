# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su (tab SLA / Phan bo cong viec): nut "Xuat Excel" va "File tong hop thang"
tai file qua fetch (03/11/2026, UX quan ly). Nut bao "Dang tao file..." khi server dang ghep
file; server tu choi (thieu quyen, ky chua co du lieu) -> cau cua server hien ngay duoi hang nut
thay vi trinh duyet bao "Tai xuong that bai" khong ro ly do. Nut cao 40px tren dien thoai.
Khong doi API (van la hr.overview.api.export_summary_xlsx), khong doi noi dung file.
Chi dong bo lai trang; tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("data-xlsx", "xlsxDownload", "kind=cnb")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p318 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p318: thieu %s" % (miss,), "p318 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p318 tong-quan sync failed")
