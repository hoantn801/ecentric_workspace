# Copyright (c) 2026, eCentric and contributors
"""p297_resync_ai_video_ban_voice: trang /ai-video (16/10/2026): tron theo voice - "So ban moi voice" (1/2/3, mac dinh 2)
- Moi voice ra N video <ten>_1.mp4, <ten>_2.mp4 voi chuoi clip noi khac nhau (player live xen ke, khong lap clip trong 15 phut).
- Bang tinh nhan so giay / so clip can co theo so ban; tong video (voice x ban) toi da 100; bang Ket qua liet ke tung ban."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p297_resync_ai_video_ban_voice: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p297_resync_ai_video_ban_voice")
