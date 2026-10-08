# Copyright (c) 2026, eCentric and contributors
"""p280_resync_ai_video_fix9: trang /ai-video - tick chon clip noi + clip SKU dung khi tron, gen lai tung clip, xuat ZIP theo SKU, luu tru/xoa du an."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p280_resync_ai_video_fix9: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p280_resync_ai_video_fix9")
