# Copyright (c) 2026, eCentric and contributors
"""p287_resync_ai_video_khung_bat_buoc: trang /ai-video - bat buoc ve khung SP truoc khi tao anh cam, 4 anh cam (2 Kie + 2 PlenX)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p287_resync_ai_video_khung_bat_buoc: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p287_resync_ai_video_khung_bat_buoc")
