# Copyright (c) 2026, eCentric and contributors
"""p298_resync_ai_video_bo_live: trang /ai-video (17/10/2026): them "Bo live" (#/kits) va "Kho host" (#/hosts).
- Bo live: brand, host, voice, che do Day du / Tiet kiem, khoang nghi 20/25/30/35s, nen (ghep san neu nen tinh),
  san pham (ma SP Shopee / TikTok), voice video khong cam / cam SP (nhieu ban v1, v2...), FAQ cap brand, cau chung;
  bam Dung Bo live -> gui may chay video (build_kit).
- Kho host: danh sach host + so clip motion, Studio anh host (model, anh tham chieu, mo ta), Gen bo motion (de xuat 20 clip,
  hien uoc tinh chi phi truoc khi bam)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p298_resync_ai_video_bo_live: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p298_resync_ai_video_bo_live")
