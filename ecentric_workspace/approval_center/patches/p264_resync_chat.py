# Copyright (c) 2026, eCentric and contributors
"""p264_resync_chat: muc menu moi "Chat noi bo" (/chat, nhom Workspace, 05/10/2026, Hoan chot
A + C - chat/).

Sidebar tinh trong HTML 3 trang (shell.fallback sinh tu registry) phai dung lai: trang chu,
Viec cua toi, Tong quan. Cung khuon voi p261.

- home: co khoa drift; ban p261 (1f9686d6...) nam trong SUPERSEDES.
- my_work, tong_quan: repo so huu toan bo byte, khong khoa drift.

O "Tin nhan" tren thanh tren KHONG nam trong file trang: no duoc them LUC RENDER (shell/server_nav)
khi chat bat, nen patch nay khong dung toi thanh tren."""
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
            log.info("p264 %s: %s" % (name, fn()))
        except Exception:
            frappe.log_error(title="p264_resync_chat: %s" % name)
