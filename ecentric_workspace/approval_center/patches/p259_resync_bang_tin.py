# Copyright (c) 2026, eCentric and contributors
"""p259_resync_bang_tin: muc menu moi "Bang tin" (/bang-tin, nhom Workspace, 04/10/2026, Hoan duyet
mockup v2 "Bang tin + Cau lac bo").

Sidebar tinh trong HTML 3 trang (shell.fallback sinh tu registry) phai dung lai: trang chu,
Viec cua toi, Tong quan. Cung khuon voi p257.

- home: co khoa drift; ban p257 (b91c748b...) nam trong SUPERSEDES.
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
            log.info("p259 %s: %s" % (name, fn()))
        except Exception:
            frappe.log_error(title="p259_resync_bang_tin: %s" % name)
