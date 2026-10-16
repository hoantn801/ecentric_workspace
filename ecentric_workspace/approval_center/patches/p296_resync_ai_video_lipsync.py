# Copyright (c) 2026, eCentric and contributors
"""p296_resync_ai_video_lipsync: trang /ai-video (13/10/2026): nut Lipsync cho dot tron theo voice (ca dot hoac tung video)
- MuseTalk + hau ky K15 tren may chay video (mo mieng theo giong, lam net, van da goc); ket qua thu muc duoi _LS.
- 16/10: dot tron SKU (B4) co voice cung lipsync duoc (ca doan cam san pham)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p296_resync_ai_video_lipsync: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p296_resync_ai_video_lipsync")
