# Copyright (c) 2026, eCentric and contributors
"""p247_resync_tin_noi_bo_tai_nguyen: muc menu "Tin noi bo" chuyen tu nhom Workspace sang nhom
Tai nguyen, THAY cho muc "Intranet (sap ra mat)" (01/10/2026, Hoan chot). O "Intranet" trong
Truy cap nhanh tren trang chu cung doi thanh "Tin noi bo" -> /tin-noi-bo.

Sidebar tinh trong HTML 3 trang (shell.fallback sinh tu registry) phai dung lai: trang chu,
Viec cua toi, Tong quan. Chay sau p246 (cung 3 trang) - p246 da chay hay chua deu duoc: sync
ghi ban hien hanh cua repo.

- home: co khoa drift; ban p241 (a347101b...) va ban p246 deu nam trong SUPERSEDES.
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
            log.info("p247 %s: %s" % (name, fn()))
        except Exception:
            frappe.log_error(title="p247_resync_tin_noi_bo_tai_nguyen: %s" % name)
