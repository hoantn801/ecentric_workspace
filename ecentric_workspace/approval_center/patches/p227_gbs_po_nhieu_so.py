# Copyright (c) 2026, eCentric and contributors
"""Form GBS PO: mot PO gom NHIEU SO - 28/10/2026 (yeu cau GBS, chi Huong).

Truoc: PO chi tao tu 1 SO (?from_so=). Nay: o che do GBS mua co khung "Them items tu SO khac"
(nam san trong HTML): chon SO cung brand da duoc GBS duyet, items cua SO do duoc them vao bang,
moi dong ghi ro thuoc SO nao (data-so + nhan). Submit / Sua & gui lai gui items[].sales_order.
Server Script (fixDS_po_nhieu_so_2026-10-28.ps1, marker v10_multi_so) kiem tung SO va dong bo
sang boxme items[].sales_order theo dung SO cua dong. parent_so = SO dau tien (tuong thich).

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = ('id="ecAddSoBox"', "window._ecPoTagRowSo = tagRowSo;", "sales_order: tr.getAttribute('data-so')")


def execute():
    from ecentric_workspace.legacy_pages.gbs_po_form_v2 import page_sync as gbs_po

    try:
        res = gbs_po.sync()
        action = (res or {}).get("action")
        frappe.log_error("p227 gbs-po-form-v2 sync=%s" % action, "p227 gbs po nhieu so")
        if action == "refused":
            frappe.log_error("p227 gbs-po-form-v2: upsert TU CHOI GHI (khoa chong troi) - live dang giu ban "
                             "khong nam trong BASELINE/SUPERSEDES.", "p227 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "gbs-po-form-v2"}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p227 gbs-po-form-v2: thieu landmark=%s" % missing, "p227 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p227 gbs-po-form-v2 failed")
