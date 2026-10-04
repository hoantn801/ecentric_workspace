# Copyright (c) 2026, eCentric and contributors
"""p258_resync_ai_video_chi_phi: trang /ai-video hien chi phi Kie ($) theo du an, SKU va moi video tron ra;
the SKU buoc Duyet anh khong con de chu len nhau."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p258_resync_ai_video_chi_phi: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p258_resync_ai_video_chi_phi")
