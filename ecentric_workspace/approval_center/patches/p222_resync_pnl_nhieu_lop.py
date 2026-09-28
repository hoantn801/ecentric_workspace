# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL: HTML server ve DUNG trang thai cuoi, khong "nhieu lop" - 28/09/2026.

Brief NHIEU_LOP/brief_pnl_sla_reports.md (chat Trang chu/Shell). Do bang
NHIEU_LOP/do_lop_trang.js tren /pnl-dashboard truoc khi sua:
  - server ve DU 5 tab roi JS moi an: trang cao 4.289 px -> 2.208 px;
  - 22 khoi co id doi cho (#pnl-team 1.031 px, #pnl-scope 238, #cp-scope 116);
  - the bo loc 140 -> 215 px: o ngay native 37,5 px bi ec_datepicker thay bang o 40 px,
    select Brand / Phong ban no rong khi do option -> Phong ban rot xuong dong 2.

Sua o markup + CSS cua trang (khong dung ec_shell / ec_datepicker, khong them khoi
<script id="ec-..."> moi):
  - khoi cua 4 tab khac mang `hidden` ngay trong HTML; applyTab() bat/tat ca `hidden`;
  - o ngay 140 x 40 px, Brand 180 px, Phong ban 240 px, hai nhan pham vi 170 px;
  - chu thich KPI giu cho 2 dong; khoi Chi phi & loi nhuan hien san;
  - chu thich bieu do dat san dung chu cua lan mo dau; giu cho khung Can de y + Cach doc so.
Do lai (chay HTML moi trong khung an tren trang live): mv 22 -> 0, the bo loc 215 -> 215.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    ".pnl-f-date{ width:140px; }",          # o ngay co dinh kich thuoc
    "els[i].hidden = !hien;",              # applyTab bat/tat hidden
    '<div id="cp-wrap">',                  # khoi chi phi hien san
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p222 pnl_dashboard sync=%s" % action, "p222 pnl nhieu lop")
        if action == "refused":
            frappe.log_error(
                "p222: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p222 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p222: thieu landmark=%s" % (missing,), "p222 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p222 failed")
