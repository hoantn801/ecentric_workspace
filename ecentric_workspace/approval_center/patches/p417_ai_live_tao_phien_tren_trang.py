# Copyright (c) 2026, eCentric and contributors
"""p417_ai_live_tao_phien_tren_trang (18/11/2026): tao / sua phien live ngay tren /ai-live (ngan ben phai, khong mo Desk).
- EC AI Live Session: ten = {may}-{ma live} (autoname format), bo unique cua live_id (2 may cung co L1 la binh thuong,
  cung 1 may thi cam - kiem o ValidateSessionService), may bat buoc. DocType sync (post_model_sync) tu doi.
- EC AI Live Machine: them hb_known_lives_json (live may da bao qua nhip tim) cho o "Live tren may".
- Sync lai Web Page /ai-live.
Luc lam (18/11) site co 0 phien -> khong doi ten ban ghi cu. Neu con phien dat ten kieu cu thi CHI ghi log de xu ly tay
(doi ten tu dong de lech lenh / lich su cua app). Chay lai vo hai."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live import page_sync as live_sync


def execute():
    log = frappe.logger("ai_tools")
    try:
        if frappe.db.table_exists("EC AI Live Session"):
            old = [r.name for r in frappe.get_all("EC AI Live Session", fields=["name", "machine", "live_id"])
                   if r.name != "%s-%s" % (r.machine or "", r.live_id or "")]
            if old:
                log.warning("p417: %d phien dat ten kieu cu (chua doi): %s" % (len(old), ", ".join(old[:20])))
    except Exception:
        frappe.log_error(title="p417_ai_live_tao_phien_tren_trang (kiem ten phien)")
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        log.info("p417_ai_live_tao_phien_tren_trang: %s" % (live_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p417_ai_live_tao_phien_tren_trang")
