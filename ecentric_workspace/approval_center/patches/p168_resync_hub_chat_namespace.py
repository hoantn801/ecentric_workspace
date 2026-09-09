# Copyright (c) 2026, eCentric and contributors
"""Popup hub: tab Trao doi bao loi + cot phai rong ra + mo san tab Trao doi (09/09, Hoan).

Loi that tren production: bam tab "Trao doi" thi hien
"module 'ecentric_workspace.approval_center.reporting.api' has no attribute 'list_comments'".
Ham `call()` cua trang tro toi `reporting.api`, con hai ham trao doi nam o `reporting.actions`
(cung cho voi get_request_detail). Goi nham khong gian ten. Gio goi qua ACT.

Cung dot (Hoan chot):
  * Cot phai rong 322px -> 400px, khung bao 1140px -> 1220px: o nhap tin nhan qua chat.
  * Tab MAC DINH la "Trao doi", ai can moi bam sang "Lich su"; binh luan duoc nap ngay khi mo
    popup chu khong doi bam tab.

Patch moi vi p166 da chay tren production. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ('ACT+"list_comments"', 'data-tab="cm" class="on"', "width:400px")


def execute():
    res = page_sync.sync()
    frappe.log_error("p168 all_requests sync=%s" % (res or {}).get("action"), "p168 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p168: hub thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
