# Copyright (c) 2026, eCentric and contributors
"""p312_resync_ai_video_truc_live: trang /ai-video (23/10/2026, fix10h): Truc live + su co + ke hoach vs thuc te.
- "Giam sat" doi thanh "Truc live" (#/monitor): bo dem lon (Dang live / KHAN / Canh bao / Mat lien lac / Lo gio hom nay),
  dai may mat lien lac, the tung live (van de to nhat + "da X phut", anh, len song bao lau, fps, AI chinh / du phong,
  chi phi hom nay so voi tran), lenh 1 cham (tam dung / chay lai AI, bo clip, phat FAQ), che do treo tuong.
- "Su co" (#/monitor/incidents): dang mo / da xac nhan / da xong, xac nhan kem ghi chu (KHAN bat buoc).
- Gantt ngay: thanh thuc te duoi khung ke hoach (Dung gio / Tre / Lo / Gian doan / Khong co bao cao)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_video import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p312_resync_ai_video_truc_live: %s" % (page_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p312_resync_ai_video_truc_live")
