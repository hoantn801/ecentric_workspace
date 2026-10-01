# Copyright (c) 2026, eCentric and contributors
"""p246_resync_home_tin_noi_bo: ra mat Tin noi bo (/tin-noi-bo, 01/10/2026, PO Hoan chot mockup v5).

Ba trang co sidebar tinh trong HTML (shell.fallback sinh tu registry) phai dung lai vi menu co
them muc "Tin noi bo": trang chu, Viec cua toi, Tong quan. Rieng trang chu doi ca khoi
"Tin noi bo": bo truy van News Post cu, doc bai qua ham Jinja internal_posts_home() (quyen
kiem phia server theo phien, ghim truoc roi moi nhat, toi da 4).

- home: co khoa drift; ban live cu (a347101b... = p241) da nam trong SUPERSEDES.
- my_work, tong_quan: repo so huu toan bo byte, khong khoa drift.
Mot trang loi khong chan migrate: ghi Error Log, trang do giu ban cu (van chay)."""
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
            log.info("p246 %s: %s" % (name, fn()))
        except Exception:
            frappe.log_error(title="p246_resync_home_tin_noi_bo: %s" % name)
