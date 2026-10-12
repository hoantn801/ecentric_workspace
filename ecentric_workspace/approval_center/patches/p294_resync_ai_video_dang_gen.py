# Copyright (c) 2026, eCentric and contributors
"""p294_resync_ai_video_dang_gen: trang /ai-video (13/10/2026): kho clip noi hien ro clip dang gen (so clip, do dai,
dang chay / cho luot, gen lai); dang gen thi khoa nut Gen them va nhac truoc khi tron."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p294_resync_ai_video_dang_gen: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p294_resync_ai_video_dang_gen")
