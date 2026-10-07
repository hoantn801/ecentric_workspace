# Copyright (c) 2026, eCentric and contributors
"""Form GBS SO: o "Store (Platform)" khong con bat buoc o che do GBS - 07/10/2026.

GBS xac nhan du an moi chua co store tren boxme thi khong can dien. Backend da tuy chon san:
GBS Sales Order.store_name reqd=0, submit_gbs_so chi luu khi co, sync_gbs_so_outgoing chi gui
custom_store khi co. Chi form chan (dau * + submit guard). Nay: che do gbsrev bo dau * va bo chan,
them goi y "de trong"; che do direct (so EC theo san) van bat buoc.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = ("var stReq = document.documentElement.getAttribute('data-ec-so-mode') !== 'gbsrev';",
           '<span class="req ec-only-direct">*</span>')


def execute():
    from ecentric_workspace.legacy_pages.gbs_so_form_v2 import page_sync as gbs_so

    try:
        res = gbs_so.sync()
        action = (res or {}).get("action")
        frappe.log_error("p226 gbs-so-form-v2 sync=%s" % action, "p226 gbs so store tuy chon")
        if action == "refused":
            frappe.log_error("p226 gbs-so-form-v2: upsert TU CHOI GHI (khoa chong troi) - live dang giu ban "
                             "khong nam trong BASELINE/SUPERSEDES.", "p226 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "gbs-so-form-v2"}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p226 gbs-so-form-v2: thieu landmark=%s" % missing, "p226 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p226 gbs-so-form-v2 failed")
