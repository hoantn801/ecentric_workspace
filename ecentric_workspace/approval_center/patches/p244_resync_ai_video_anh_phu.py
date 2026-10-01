# Copyright (c) 2026, eCentric and contributors
"""p244_resync_ai_video_anh_phu: trang /ai-video them o tai anh phu cac mat (toi da 4) cho moi
SKU, gui kem anh chinh dien cho AI tao anh cam / master (worker n8n v5.10)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p244_resync_ai_video_anh_phu: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p244_resync_ai_video_anh_phu")
