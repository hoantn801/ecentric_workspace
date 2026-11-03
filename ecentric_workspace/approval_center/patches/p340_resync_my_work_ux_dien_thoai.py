# Copyright (c) 2026, eCentric and contributors
"""p340: resync /viec-cua-toi sau dot UX dien thoai (03/11/2026, ux2).

Nguon trang doi: huy hieu header doi ngay sau khi duyet nhanh, tab Thong bao co thoi gian + chu
tron + danh dau da doc, han viec bang chu ("Hom nay", "Qua 3 ngay"), loi tieng Viet, mat mang tu
tai lai, vung cham >= 44px. page_sync.sync() tu gan lai thanh tab duoi (_with_tab_bar). Tu kiem:
con thanh tab + con khoi Cho toi duyet. Loi chi ghi log, khong bao gio nem."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    try:
        res = my_work.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": my_work.ROUTE}, "main_section_html") or ""
        frappe.log_error(title="p340 viec-cua-toi UX dien thoai",
                         message="sync=%s thanh_tab=%s cho_duyet=%s huy_hieu=%s" % (
                             res.get("action"), "ec-tabbar-shared-v1" in html,
                             "data-ec-cho-duyet" in html, "syncHeaderBadge" in html))
    except Exception:
        frappe.log_error(title="p340_resync_my_work_ux_dien_thoai", message=frappe.get_traceback())
