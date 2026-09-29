# Copyright (c) 2026, eCentric and contributors
"""/ec-fee-review: giu cho cho khoi tao moi - 29/09/2026.

Brief NHIEU_LOP/brief_gbs.md muc 6. Do bang NHIEU_LOP/do_lop_trang.js truoc khi sua: #ecfr-create
lech 279 px (nut nam DUOI bang, bang dai ra khi danh sach tai xong), #ecfr-body 22, #ecfr-all 11.
Sua o NGUON trang (A65; nguon vua dua ve repo o commit truoc):
  - khoi "Tao Item EC cho ma da chon" len TREN bang;
  - bang table-layout:fixed + <colgroup> -> header khong xo lech khi hang du lieu ve.
JS khong doi. Trang van KHONG co khung chung (menu) - gan hay khong cho PO quyet.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = ('id="ecfr-actions"', "table-layout:fixed")


def execute():
    from ecentric_workspace.legacy_pages.ec_fee_review import page_sync as fr

    try:
        res = fr.sync()
        action = (res or {}).get("action")
        frappe.log_error("p225 ec-fee-review sync=%s" % action, "p225 ec-fee-review")
        if action == "refused":
            frappe.log_error(
                "p225 ec-fee-review: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong "
                "nam trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha trong ket "
                "qua roi them vao SUPERSEDES_SHA256.", "p225 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "ec-fee-review"}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p225 ec-fee-review: thieu landmark=%s" % missing, "p225 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p225 ec-fee-review failed")
