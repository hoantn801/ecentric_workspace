# Copyright (c) 2026, eCentric and contributors
"""p259_resync_ai_video_khung_sp: trang /ai-video co hop ve khung san pham len anh host (buoc 1 + gen lai
o buoc 2, so khung tren anh cam), tab Prompt them prompt theo nhom SP; chi role EC AI Video Admin sua prompt."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p259_resync_ai_video_khung_sp: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p259_resync_ai_video_khung_sp")
