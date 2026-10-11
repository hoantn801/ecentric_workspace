# Copyright (c) 2026, eCentric and contributors
"""p291_resync_ai_video_cong_thuc: trang /ai-video - cong thuc prompt theo brand + dong SP (tab Prompt), SKU chon
cong thuc o buoc 1, goi y khung trong cua so ve khung; khung so co tren ca 4 anh cam = 100%."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p291_resync_ai_video_cong_thuc: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p291_resync_ai_video_cong_thuc")
