# Copyright (c) 2026, eCentric and contributors
"""Hub /approvals: dai "N phieu dang cho ban duyet" o dau trang (03/11/2026, UX quan ly).

Truoc dot nay nguoi duyet mo Approval Center chi thay danh muc TAO yeu cau; phieu dang cho chinh
ho duyet nam o /viec-cua-toi, khong co loi vao nao tu hub. Nay hub goi DUNG cua "Viec cua toi"
(reporting.actions.list_my_pending - GET, server chi tra phieu cho chinh nguoi dang nhap o cap
hien tai) de dem, va ve mot dai bam duoc dan sang /viec-cua-toi#mw-cho-duyet. Co phieu qua han
-> dai do + "N phieu da qua han". Khong co phieu / loi mang -> dai an, danh muc khong anh huong.

CHI doi HTML/CSS/JS cua trang hub. Khong doi API, khong doi workflow, khong doi phan quyen,
khong co nut quyet dinh o hub (duyet van o /viec-cua-toi hoac trang chi tiet).

Dong thoi dua resync_manifest cua hub ve dung (p189 doi template ma khong cap nhat manifest).
Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync

_LANDMARKS = (
    'id="apc-mine"',
    "reporting.actions.list_my_pending",
)


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p317 hub sync=%s" % action, "p317 resync")
    if action == "refused":
        frappe.log_error(
            "p317: upsert TU CHOI GHI (live drift) - trang KHONG duoc cap nhat. "
            "Chay verify_approvals_baseline.ps1 roi doi chieu SUPERSEDES_SHA256.",
            "p317 REFUSED")
        return

    html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p317: trang hub thieu dau moc %s" % thieu, "p317 KHONG toi noi")
