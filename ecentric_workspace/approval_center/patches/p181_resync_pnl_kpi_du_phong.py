# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL: KPI Tong quan chi cong thang NAM TRONG KY - 11/09, Hoan phat hien.

Nut "Du phong +3 thang toi" nam o tab OPEX keo dai date_to cua RIENG API chi phi
(costArgs()), doanh thu thi giu nguyen ky da chon. Khoi KPI o tab Tong quan lai cong
HET moi thang API chi phi tra ve -> doanh thu 1 thang tru chi phi 4 thang.

Thang 08/2026 hien: quy luong 5,56 ty (that ra 1,39 ty x 4 thang), tong chi phi 6,11 ty,
loi nhuan -2,26 ty, bien -58,9%. Toan bo la so bia, tren dung trang CEO xem. Va vi nut do
nam o TAB KHAC nen dung o Tong quan khong ai thay ly do.

Sua o phia trang: them trongKy() loc theo thang lay tu meta cua API doanh thu, ap cho ca
KPI lan bieu do co cau chi phi. Loc theo thang chan tan goc - du API tra ve rong hon vi bat
cu ly do gi thi KPI van chi cong dung ky.

Kiem bang Chromium that voi hai kich ban (API tra ve 4 thang / 1 thang): ca hai deu ra
3,85 ty doanh thu, 1,94 ty chi phi, 1,91 ty loi nhuan, bien 49,6% - tuc KPI khong con phu
thuoc nut Du phong nua.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    "function trongKy",      # ham loc thang
    "trongKy(pc[i].month)",  # KPI chi cong thang trong ky
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p181 pnl_dashboard sync=%s" % action, "p181 pnl kpi")
        if action == "refused":
            frappe.log_error(
                "p181: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p181 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p181: thieu landmark=%s" % (missing,), "p181 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p181 failed")
