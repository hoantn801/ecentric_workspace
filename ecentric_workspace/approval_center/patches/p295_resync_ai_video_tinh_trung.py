# Copyright (c) 2026, eCentric and contributors
"""p295_resync_ai_video_tinh_trung: trang /ai-video (13/10/2026): bang tinh clip noi - canh rieng can = T(1 - % trung),
100% = khong can gen them; moi dot tron mac dinh 1 thu muc rieng; canh bao khi tron vao thu muc da co video."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p295_resync_ai_video_tinh_trung: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p295_resync_ai_video_tinh_trung")
