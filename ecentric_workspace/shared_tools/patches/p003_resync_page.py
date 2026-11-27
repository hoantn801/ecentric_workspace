# Copyright (c) 2026, eCentric and contributors
"""p003: dong bo lai trang /kalodata (asset ?v= doi: danh sach "File da xuat cua toi" gon mot dong, nut Tai
luon thay, khong con cuon ngang). Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p003 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p003_resync_page")
