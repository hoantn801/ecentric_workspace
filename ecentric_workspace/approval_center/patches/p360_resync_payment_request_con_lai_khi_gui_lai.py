# Copyright (c) 2026, eCentric and contributors
"""De nghi thanh toan chia dot: "Bo sung & gui lai" dot 2 tinh sai phan con lai (12/11/2026, Hoan).

EC-PAYR-2026-00652 (dot 2, 170.208.000d / tong 220.208.000d, dot 1 da chi 50.000.000d) bi tra ve bo
sung -> mo form gui lai thay "Da de nghi cac dot truoc 0d / con lai 50.000.000d" va doi nhap dot 3.
Nguyen nhan: startEditResubmit khong tinh _paid_before (chi startEditDraft co). Server
(validate_installment / paid_before) van dung. Sua: ham chung setPaidBefore goi o ca hai nhanh.
Patch chi resync trang form. KHONG BAO GIO nem loi.
"""
import frappe

_EXPECT = ("function setPaidBefore(det)", 'state.mode="edit";\n    setPaidBefore(det);')


def execute():
    try:
        from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
        res = page_sync.sync() or {}
        if res.get("action") == "refused":
            frappe.log_error("p360: upsert TU CHOI GHI (khoa chong troi) live_sha=%s" % res.get("live_sha"),
                             "p360 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        thieu = [m for m in _EXPECT if m not in html]
        if thieu:
            frappe.log_error("p360: thieu landmark=%s" % (thieu,), "p360 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p360 resync payment request")
