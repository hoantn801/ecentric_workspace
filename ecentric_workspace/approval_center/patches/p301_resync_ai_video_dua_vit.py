# Copyright (c) 2026, eCentric and contributors
"""p301_resync_ai_video_dua_vit: trang /ai-video (18/10/2026): dua vit trong live (W20).
- "Dua vit" (#/races): moi cuoc dua cua cac brand (nguoi thang, phan qua, trang thai trao giai, anh ket qua, ma kiem tra),
  loc brand / phien live / khoang ngay / ket qua / trao giai, xuat CSV, cap nhat trao giai tung nguoi hoac hang loat, ghi chu.
- Chi tiet phien: tab "Giai thuong (dua vit)" (#/live/<ma>/giai); nut "Dua vit..." (tu khoa, thoi gian, giai lan nay)
  va "Dung dua vit" gui lenh cho app.
- Bo live / Clip chung: them 4 nhom dua vit (moi tham gia, binh luan luc dua, chuc mung khong ten, cach nhan qua)
  kem loi goi y; tha file dua_moi_1 / dua_binhluan_1 / dua_chucmung_1 / dua_nhanqua_1."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p301_resync_ai_video_dua_vit: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p301_resync_ai_video_dua_vit")
