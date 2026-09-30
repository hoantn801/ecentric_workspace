# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL 5 tab - sua sau khi Hoan xem ban dau (30/09/2026).

  - Khoi "khoan keo len / keo xuong" bi vo hang: class .row dung voi .row cua Bootstrap tren site
    (margin am, con 100% rong) -> doi ten .mv-row;
  - Chi phi van hanh T1-T8 tach san theo nhom (lay tu chi tiet so P&L, xem EXP_HIST trong ec_pnl_bao_cao);
  - Thang dang chay: chi phi lay so lon hon giua DNTT da duyet va muc toi thieu (ty le 3 thang gan nhat),
    vi DNTT ve cham lam loi nhuan thang dang chay cao gia;
  - Tieu de trang ghi ro dang xem khach hang / brand nao khi chon "Theo brand".

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    'class="mv-row"',                      # khoi keo len / keo xuong khong dung .row cua Bootstrap
    'method: method, args: args || {}',    # frappe.call GET
    '"ec_pnl_bao_cao"',                    # API moi
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p238 pnl_dashboard sync=%s" % action, "p238 pnl 5 tab moi")
        if action == "refused":
            frappe.log_error(
                "p238: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p238 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p238: thieu landmark=%s" % (missing,), "p238 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p238 failed")
