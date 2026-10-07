# Copyright (c) 2026, eCentric and contributors
"""p273_resync_ai_video_fix8: trang /ai-video mo du an ngay (dong bo may chay video o nen), nut co trang thai dang xu ly,
bat chay dem khong loi, nhap hang loat (dan Excel + keo tha anh/audio), khoi luong SP, bang chi phi chi tiet."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p273_resync_ai_video_fix8: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p273_resync_ai_video_fix8")
