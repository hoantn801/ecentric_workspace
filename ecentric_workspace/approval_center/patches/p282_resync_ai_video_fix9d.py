# Copyright (c) 2026, eCentric and contributors
"""p282_resync_ai_video_fix9d: trang /ai-video - bang Ket qua tron ghi "theo audio" thay vi do dai mac dinh du an."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p282_resync_ai_video_fix9d: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p282_resync_ai_video_fix9d")
