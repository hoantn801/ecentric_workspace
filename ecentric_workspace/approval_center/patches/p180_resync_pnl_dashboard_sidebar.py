# Copyright (c) 2026, eCentric and contributors
"""Dashboard PnL: day markup moi len Web Page record - 11/09, Hoan.

Hai dot sua truoc do KHONG kem patch resync, nen deploy xong trang van chay markup cu:
  - e3f2e49  bo nut "Ap dung" (bo loc tu chay), hoan ve bieu do o tab dang an
  - 7ccb1c7  gan tab vao hash de sidebar phu cua trang (context `pnl`) dieu khien duoc

Trang KHONG duoc phuc vu tu dia: page_sync BOM markup vao Web Page `doanh-thu-ecentric`.
Sua file trong git roi deploy thi khong ai thay gi ca. Dung lo ra dung kieu do: sau khi
deploy, sidebar 5 muc hien ra (do la code Python, len ngay) nhung bam vao thi noi dung
khong doi - vi JS tren trang van la ban cu, chua co phan nghe hashchange. Mot nua tinh
nang len, mot nua khong, va nhin qua thi tuong tinh nang hong.

`test_html_change_needs_resync` da bat duoc dieu nay; no chi do vi khong ai chay no.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = (
    "tabTuHash",      # hash la nguon su that duy nhat cho tab dang xem
    "hashchange",     # doi hash -> doi dashboard, khong tai lai trang
    "bindTuDong",     # bo loc tu chay, khong con nut "Ap dung"
)


def execute():
    from ecentric_workspace.reporting.pnl_dashboard import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p180 pnl_dashboard sync=%s" % action, "p180 pnl sidebar")
        if action == "refused":
            frappe.log_error(
                "p180: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p180 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "pnl-dashboard"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p180: thieu landmark=%s" % (missing,), "p180 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p180 failed")
