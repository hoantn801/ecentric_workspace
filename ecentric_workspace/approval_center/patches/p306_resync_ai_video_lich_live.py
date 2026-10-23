# Copyright (c) 2026, eCentric and contributors
"""p306_resync_ai_video_lich_live: trang /ai-video (23/10/2026, fix10g): quan ly lich live 4 kieu xem + ban nhap -> phat hanh.
- Lich live co 4 tab: "Gantt ngay" (#/schedule/day - moi dong 1 may phat, chia theo kenh OBS, vach gio hien tai,
  trang thai may nhan lich), "Tuan" (#/schedule), "Thang" (#/schedule/month - so lan live, luc dong nhat / suc chua may,
  gio live theo brand), "Dong bo" (#/schedule/sync - ban nhap cho phat hanh, kiem tra, giu gio cu, may nhan lich,
  nhat ky phat hanh ca thay doi do app gui ve).
- Moi sua doi (keo tha, form khung, doi may / kenh OBS) vao ban nhap; app tren may chi nhan khi bam Phat hanh.
- Khoi "nhap" (vien net dut), "giu gio cu" (soc), canh bao dong ho may lech."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p306_resync_ai_video_lich_live: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p306_resync_ai_video_lich_live")
