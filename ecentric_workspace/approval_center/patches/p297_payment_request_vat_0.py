# Copyright (c) 2026, eCentric and contributors
"""De nghi thanh toan: them thue suat VAT 0% (13/10/2026, Hoan).

`ec_vat_pct` truoc co "0" (Khong co VAT) / "8" / "10". Hoa don thue suat 0% (vd dich vu xuat
khau) khac "khong co VAT" ve chung tu nen tach thanh lua chon rieng, gia tri luu "0.0":
  * PnL (ec_pnl_chi_phi / ec_pnl_bao_cao) CAST ra so -> 0, chia (1 + 0/100) -> khong doi so lieu;
  * "0" van la mac dinh, phieu cu giu nguyen.

Hai viec: (1) them "0.0" vao options cua Custom Field (fixtures cung da sua, day la luoi cho
truong hop fixtures chua dong bo - patch chay TRUOC sync_fixtures); (2) resync trang form.
KHONG BAO GIO nem loi: exception trong migrate lam chet ca lan deploy (p116).
"""
import frappe

_CF = "EC Payment Request-ec_vat_pct"
_OPTIONS = "0\n0.0\n8\n10"
_EXPECT = ('<option value="0.0"', 'data-model="ec_vat_pct"')


def execute():
    try:
        if frappe.db.exists("Custom Field", _CF):
            if (frappe.db.get_value("Custom Field", _CF, "options") or "") != _OPTIONS:
                frappe.db.set_value("Custom Field", _CF, "options", _OPTIONS)
                frappe.clear_cache(doctype="EC Payment Request")
        else:
            frappe.log_error("p297: khong thay Custom Field %s" % _CF, "p297 VAT 0%")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p297 custom field")
    try:
        from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
        res = page_sync.sync() or {}
        if res.get("action") == "refused":
            frappe.log_error("p297: upsert TU CHOI GHI (khoa chong troi) live_sha=%s" % res.get("live_sha"),
                             "p297 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        thieu = [m for m in _EXPECT if m not in html]
        if thieu:
            frappe.log_error("p297: thieu landmark=%s" % (thieu,), "p297 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p297 resync payment request")
