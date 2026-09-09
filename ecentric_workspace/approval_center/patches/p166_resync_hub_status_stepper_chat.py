# Copyright (c) 2026, eCentric and contributors
"""Popup hub: trang thai dung thuc te, tien trinh du buoc, khung trao doi (09/09, Hoan).

Bon loi that tren production:
  * Phieu dang o buoc Operation van hien "Hoan tat" - statusCell chi ghep buoc xu ly vao khi
    dang o tab "Cho toi xu ly"; tab khac hien trang thai duyet, ma duyet xong = Approved.
  * Cot "Cap hien tai" in ra so 0 (duyet xong thi current_level ve 0).
  * Tien trinh trong popup thieu "Da gui" / buoc xu ly / "Hoan tat".
  * Ba nguoi da duyet ma moi cap hien nhu chua ai xu ly: chot cu la
    `level_status==="Completed"` - GIA TRI DO KHONG TON TAI (options that: Pending /
    In Progress / Approved / Rejected / Skipped / Information Requested). Ve dau luon sai, ve
    con lai `level_no < cur` cung tat khi cur = 0 -> popup chua bao gio ve dung cho phieu da
    duyet.

Cung dot:
  * Bam vao khoang trong GIUA/DUOI hai the cung dong popup (truoc chi bam dung lop phu moi
    dong; khoang trong do la .ec-apl-wrap chu khong phai lop phu).
  * Cot phai thanh HAI TAB: "Lich su" va "Trao doi" (Hoan chon phuong an A, 09/09). Trao doi
    dung Frappe Comment gan vao ho so nghiep vu, gac bang can_view_request - ai xem duoc phieu
    thi doc/gui duoc, khong ai khac. Luu VAN BAN THUAN (Comment la truong HTML).

Patch moi vi cac patch resync truoc da chay tren production. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("function ffActive(r)", "function levelCell(r)", 'data-tab="cm"',
              "function loadComments(")


def execute():
    res = page_sync.sync()
    frappe.log_error("p166 all_requests sync=%s" % (res or {}).get("action"), "p166 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p166: hub thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
