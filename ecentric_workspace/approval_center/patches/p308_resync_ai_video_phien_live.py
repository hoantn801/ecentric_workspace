# Copyright (c) 2026, eCentric and contributors
"""p308_resync_ai_video_phien_live: trang /ai-video (18/10/2026): them quan ly phien live tren ERP.
- "Phien live" (#/lives): danh sach moi phien (brand, san, may, trang thai, khung ke tiep, nguoi xem, chi phi hom nay,
  dang phat), loc brand / san / may / trang thai, bat-tat hang loat; nut "Xem nhu khach" (#/watch): tuong anh phia
  khach cua moi phien dang live (anh tu san -> luong TikTok -> dien thoai), nhan nguon + tuoi anh, mat hinh > 2 phut.
- "Lich live" (#/schedule): lich tuan theo may hoac brand, keo de tao / doi gio, khoi do khi may vuot so live toi da,
  chep tuan; ban dien thoai hien dang danh sach theo ngay.
- Chi tiet phien (#/live/<ma>): dang phat + tien do, sap phat, hang cau hoi, comment gan day, loi chao, bao dong,
  bieu do, anh OBS / san, chi phi hom nay, nut tam dung / tiep tuc AI, bo clip, phat FAQ ngay; tom tat cac phien da xong.
- "Lich su phien" (#/history): tom tat cuoi phien (thoi luong, comment, da tra loi, loi chao, chi phi).
- Chu hien cho nguoi dung ve lipsync (Tao Bo live, dot AI Video) ghi trung tinh, khong neu nha cung cap / model."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p308_resync_ai_video_phien_live: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p308_resync_ai_video_phien_live")
