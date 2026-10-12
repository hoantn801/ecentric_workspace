# Copyright (c) 2026, eCentric and contributors
"""p292_resync_ai_video_faq: trang /ai-video tach flow (12/10/2026): buoc 0 Host & khung neo (gen 4 ung vien PlenX, chon 1)
roi 2 nhanh - A. Video chi noi (theo voice / theo do dai, bang tinh % trung khung, do giat) va B. Video cam SP (nhu cu,
anh cam lam tu khung neo). Quan tri chon host co san; toi da 150 luot clip noi."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p292_resync_ai_video_faq: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p292_resync_ai_video_faq")
