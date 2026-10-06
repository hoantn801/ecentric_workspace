# Copyright (c) 2026, eCentric and contributors
"""p257_resync_gop_y: muc menu "Gop y BGD (sap ra mat)" -> "Gop y cong ty" (/gop-y, 04/10/2026,
Hoan chot). O "Gop y BGD" trong Truy cap nhanh tren trang chu cung doi thanh "Gop y cong ty" -> /gop-y.

Sidebar tinh trong HTML 3 trang (shell.fallback sinh tu registry) phai dung lai: trang chu,
Viec cua toi, Tong quan. Cung khuon voi p247.

- home: co khoa drift; ban p248 (515b9521...) nam trong SUPERSEDES.
- my_work, tong_quan: repo so huu toan bo byte, khong khoa drift."""
import frappe


def _home():
    from ecentric_workspace.legacy_pages.home import page_sync
    return page_sync.sync()


def _my_work():
    from ecentric_workspace.action_center.pages.my_work import page_sync
    return page_sync.sync()


def _tong_quan():
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    return page_sync.sync()


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    log = frappe.logger("approval_center")
    for name, fn in (("home", _home), ("my_work", _my_work), ("tong_quan", _tong_quan)):
        try:
            log.info("p257 %s: %s" % (name, fn()))
        except Exception:
            frappe.log_error(title="p257_resync_gop_y: %s" % name)
