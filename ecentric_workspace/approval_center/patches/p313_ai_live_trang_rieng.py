# Copyright (c) 2026, eCentric and contributors
"""p313_ai_live_trang_rieng (25/10/2026): AI Live tach khoi /ai-video thanh trang rieng /ai-live "Quan ly AI Live".
- Tao Web Page /ai-live (Truc live, Su co, Phien live, Lich live, Lich su phien, Dua vit, Bo live & Kho host, Tuong hinh).
- Sync lai /ai-video (bo phan AI Live; link cu #/monitor, #/lives, #/kits... tu chuyen sang /ai-live) va /ai-usage
  (menu tinh co muc "Quan ly AI Live"). Moi trang sync rieng, loi trang nay khong chan trang kia."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live import page_sync as live_sync
from ecentric_workspace.ai_tools.pages.ai_usage import page_sync as usage_sync
from ecentric_workspace.ai_tools.pages.ai_video import page_sync as video_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for name, mod in (("ai-live", live_sync), ("ai-video", video_sync), ("ai-usage", usage_sync)):
        try:
            frappe.logger("ai_tools").info("p313_ai_live_trang_rieng %s: %s" % (name, mod.sync() or {}))
        except Exception:
            frappe.log_error(title="p313_ai_live_trang_rieng " + name)
