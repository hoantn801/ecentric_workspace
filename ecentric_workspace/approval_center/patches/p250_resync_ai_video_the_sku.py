# Copyright (c) 2026, eCentric and contributors
"""p250_resync_ai_video_the_sku: trang /ai-video - the SKU o buoc Duyet anh: ma SKU dai + nhan trang thai
khong con de len nhau (header the cho xuong dong)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p250_resync_ai_video_the_sku: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p250_resync_ai_video_the_sku")
