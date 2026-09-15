# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL: day khoi "Chi phi & loi nhuan" len Web Page record - 10/09, Hoan.

PR #507 doi `reporting/frontend/pnl_dashboard.main_section.html` (them khoi chi phi, tab
"Theo loai chi phi", canh bao phieu chua phan loai, dong tien bi loai tru) va co bump
BASELINE_SHA256 trong page_sync.py, NHUNG khong kem patch resync va khong cap nhat
`resync_manifest.json`. Trang KHONG duoc phuc vu tu dia - page_sync BOM markup vao record
Web Page `doanh-thu-ecentric` - nen sua file thoi thi mot site dung lai tu dau se ket o ban
markup do p047 tao nam ngoai.

Tren team.ecentric.vn thi trang van dung: dot do da sync thang qua REST (`upsert_web_page`),
live sha = 2c8ebf65... = ban trong repo, ca bon moc duoi deu co mat. Patch nay KHONG chua bug
dang thay tren production; no dong lai cho ho de bench moi / site dung lai cung nhan duoc
markup nay, va de `test_html_change_needs_resync` het do.

Idempotent: sync() se tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    "cp-k-profit",     # o KPI loi nhuan = doanh thu - quy luong - chi phi khac
    "otherByGroup",    # gom chi phi khac theo NHOM cua EC Loai Chi Phi
    "cp-oc-warn",      # canh bao phieu chua gan loai chi phi
    "cp-oc-excl",      # dong "co tien ra nhung khong tinh vao chi phi ky nay"
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p175 pnl_dashboard sync=%s" % action, "p175 pnl dashboard")
        if action == "refused":
            frappe.log_error(
                "p175: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p175 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p175: thieu landmark=%s" % (missing,), "p175 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p175 failed")
