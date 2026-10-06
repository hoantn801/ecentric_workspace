# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL: popup chi tiet chi phi hoat dong - 01/10/2026.

Hoan: bam vao bieu do "Chi phi hoat dong theo nhom" (tab Nhan su & chi phi) thi hien popup cac khoan chi
(ten khoan, phieu, phong, so tien, %), xep tu cao xuong thap. Du lieu tu ec_pnl_bao_cao.cost.opex_items:
thang <= 08/2026 lay tung dong chi phi trong so P&L, tu 09/2026 lay tung DNTT da duyet. Khoan "nhan su khac"
khong hien noi dung (co the co ten nguoi).

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    'ec-pnl-pop',                          # popup chi tiet chi phi
    'method: method, args: args || {}',    # frappe.call GET
    '"ec_pnl_bao_cao"',                    # API moi
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p245 pnl_dashboard sync=%s" % action, "p245 pnl popup chi phi")
        if action == "refused":
            frappe.log_error(
                "p245: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p245 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p245: thieu landmark=%s" % (missing,), "p245 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p245 failed")
