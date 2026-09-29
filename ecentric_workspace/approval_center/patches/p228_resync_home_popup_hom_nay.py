# Copyright (c) 2026, eCentric and contributors
"""Trang chu: popup "Hom nay o eCentric" + trang tri ngay sinh nhat - PO Hoan chot 29/09/2026.

Nguon trang them (xem home_today/ va NHIEU_LOP/brief_popup_su_kien.md):
  * MOT dong nap asset: bundled_asset('ec_home_popup.bundle.js') defer (popup noi, khong dung
    vao bo cuc; thay popup chao ban moi rieng cua HR - ec_welcome_popup.js khong nap);
  * co data-ec-today tren .ec2-home: server noi truoc co noi dung khong -> khong goi API thua;
  * trang tri sinh nhat ve SAN theo nguoi xem (ham Jinja home_today_celebration): ca cong ty
    day co + nhan / cung phong + bong bay / nguoi sinh nhat dai le hoi + phao giay. Lop noi
    (absolute / fixed), khong doi kich thuoc gi.

Chi goi legacy_pages.home.page_sync.sync() (khoa chong troi: live phai dang la ban p227
7bfda03c hoac cac ban truoc; render thu Jinja truoc khi ghi). Tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("ec_home_popup.bundle", 'data-ec-today="')


def execute():
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p228 home sync=%s" % action, "p228 trang chu popup hom nay")
        if action == "refused":
            frappe.log_error("p228: upsert TU CHOI GHI (khoa chong troi): %s" % (res,), "p228 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p228: thieu %s" % (miss,), "p228 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p228 home sync failed")
