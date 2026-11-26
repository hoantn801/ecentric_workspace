# Copyright (c) 2026, eCentric and contributors
"""p571_tai_san_trang: dua 6 trang Quan ly tai san len site (Hoan 26/11/2026).

/tai-san, /tai-san/thiet-bi, /tai-san/luan-chuyen, /tai-san/sua-chua, /tai-san/kiem-ke,
/tai-san/cua-toi - nguon trong tai_san/pages/*, asset public/tai_san/*. Route dang bi trang khac
giu thi doi sang <route>-cu (khong xoa), xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p571 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p571_tai_san_trang")
