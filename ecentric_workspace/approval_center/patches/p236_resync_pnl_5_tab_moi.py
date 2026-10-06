# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL lam lai 5 tab - 29/09/2026.

Hoan duyet ban mau (artifact S4cr8aEXeEhhjgFXuGx3Hk) va "xu li full luon":
  - 5 tab: Tong quan, Brand, Nhan su & chi phi, Du bao, Bao cao (P&L + Dong tien);
  - so lieu tu Server Script moi `ec_pnl_bao_cao` (doanh thu + chi phi theo brand,
    khach hang me, nhom chi phi, quy luong theo chuc danh / phong ban, dong tien),
    cong them phi van hanh gian hang tu `ec_pnl_phi_ql`; `ec_pnl_chi_phi` chi con
    dung cho tuyen dung / nghi viec va pham vi quan ly phong ban;
  - dau "!" giai thich tung truong, % tren cot chong, phong ban theo ERP,
    brand gom theo Khach hang me voi ten de doc;
  - hash cu (#doanh-thu, #chi-phi, #opex) tu chuyen sang tab moi.
Giu luat NHIEU_LOP: server ve san cac tab (tab khac mang `hidden`), khong them
<script id="ec-..."> moi (dung lai ec-pnl-dashboard), khong dung .ec-shell-mount.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    'data-tb="du-bao"',                    # tab Du bao moi
    'method: method, args: args || {}',    # frappe.call GET
    '"ec_pnl_bao_cao"',                    # API moi
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p236 pnl_dashboard sync=%s" % action, "p236 pnl 5 tab moi")
        if action == "refused":
            frappe.log_error(
                "p236: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p236 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p236: thieu landmark=%s" % (missing,), "p236 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p236 failed")
