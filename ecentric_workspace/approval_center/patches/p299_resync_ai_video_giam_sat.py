# Copyright (c) 2026, eCentric and contributors
"""p299_resync_ai_video_giam_sat: trang /ai-video (18/10/2026): them "Giam sat live" (#/monitor).
- Tuong o: moi live tren moi may phat 1 o (anh OBS + anh dien thoai neu co, mau do / vang / on / ngoai gio,
  khung/giay, % rot khung, % GPU, kbps, comment gan nhat, bao dong gan nhat); loc theo muc + brand; tu lam moi 15 s.
- Bam o: chi tiet (bieu do 1 gio, lich su bao dong 24 gio). Nut "Gui thu bao dong" + link Cai dat bao dong.
- Bo live (#/kit/<ten>): muc "Clip chung" 4 loai - chao chung (3-5), cam on / hen gioi thieu lai (3), tra loi chung (2),
  cau cho (3, khi doc lai cau hoi bi tre) - kem loi goi y sua duoc de thu am / TTS, so ban nen co; tha file cho_1.mp3.
- Duoc dung voi API push_heartbeat / monitor_* va cron moi phut bao Teams / Zalo khi may mat tin hieu."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p299_resync_ai_video_giam_sat: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p299_resync_ai_video_giam_sat")
