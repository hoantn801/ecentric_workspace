# Copyright (c) 2026, eCentric and contributors
"""p286_resync_ai_video_host_seat: trang /ai-video - tao anh host ngoi ban tu anh chan dung (Cai dat du an)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p286_resync_ai_video_host_seat: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p286_resync_ai_video_host_seat")
