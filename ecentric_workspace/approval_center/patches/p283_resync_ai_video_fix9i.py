# Copyright (c) 2026, eCentric and contributors
"""p283_resync_ai_video_fix9i: trang /ai-video - chon nha cung cap AI (Kie / PlenX) trong Cai dat du an."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p283_resync_ai_video_fix9i: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p283_resync_ai_video_fix9i")
