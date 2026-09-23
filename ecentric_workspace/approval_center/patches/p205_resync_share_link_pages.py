# Copyright (c) 2026, eCentric and contributors
"""Nut "Mo online" dung LINK CHIA SE thay vi URL goc cua tep (23/09).

Hai trang hien dinh kem SharePoint: form Contract Review va ngan xem nhanh cua
/approvals/all-requests. Ca hai doi sang `sp_share_url || sp_web_url` - ban ghi cu chua co link
(truoc khi p204 chay xong) van mo duoc nhu truoc, khong lam mat duong nao dang dung.

Landmark = dieu PHAI CO tren ban song sau khi sync. Xem F11 trong 03_BUGS_AND_NEXT_STEPS.md:
log cua patch resync da tung khong ra dong nao - kiem that bang cach doc main_section_html.
"""
import frappe

_TRANG = (
    ("ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync",
     "approvals/contract-review", "f.sp_share_url||f.sp_web_url"),
    ("ecentric_workspace.approval_center.ui.all_requests.page_sync",
     "approvals/all-requests", "a.sp_share_url||a.sp_web_url"),
)


def execute():
    ket = []
    for mod_path, route, moc in _TRANG:
        try:
            res = frappe.get_module(mod_path).sync()
            action = (res or {}).get("action")
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            ket.append("%s: %s, dau moc %s" % (route, action, "CO" if moc in html else "THIEU"))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p205 resync %s" % route)
            ket.append("%s: LOI" % route)
    frappe.log_error("; ".join(ket), "p205 resync share link")
