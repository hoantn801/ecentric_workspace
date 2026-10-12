# Copyright (c) 2026, eCentric and contributors
"""p293_resync_ai_video_gen_khi_bam: trang /ai-video (12/10/2026 toi): chot khung neo xong KHONG tu gen clip noi - chi gen khi
bam Gen them (bang tinh tu tinh mix do dai 10/8/6s khit voice) hoac Bo qua (so mac dinh); clip loi QC hien rieng, mau xam, khong tick;
thong ke kho clip tu doc lai khi so clip doi."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p293_resync_ai_video_gen_khi_bam: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p293_resync_ai_video_gen_khi_bam")
