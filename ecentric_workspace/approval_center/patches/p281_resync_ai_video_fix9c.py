# Copyright (c) 2026, eCentric and contributors
"""p281_resync_ai_video_fix9c: trang /ai-video - chon anh/mp3 khong phai bam 2 lan, bao SKU trung khi luu."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p281_resync_ai_video_fix9c: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p281_resync_ai_video_fix9c")
