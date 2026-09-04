# Copyright (c) 2026, eCentric and contributors
"""Nut "Ket noi SCTS" mau xanh la ngay tren Approval Center (/approvals).

Y Hoan 04/09: ket noi tai khoan ky so mot lan o hub cho tien, thay vi phai mo mot phieu.
Nut chi hien cho nguoi CAN ket noi (co mapping, khong phai tai khoan tich hop); xanh la khi
chua ket noi, xam nhat "da ket noi - con N ngay" khi da ket noi. Popover nhap mat khau SCTS
mot lan -> POST api.link_scts_account_me -> ERP giu token, khong luu mat khau.

Khoa chong troi: live sha do duoc 04/09 (0a0283...) da them vao SUPERSEDES_SHA256 cua
ui/hub/page_sync.py - khong force. Tu VERIFY landmark; refused thi nem.
"""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync

_LANDMARK = 'id="apc-scts-form"'


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p140 hub sync=%s live=%s" % (action, str((res or {}).get("live_sha"))[:12]),
                     "p140 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p140: /approvals van chua co nut Ket noi SCTS sau sync (action=%s, "
                        "live_sha=%s)" % (action, (res or {}).get("live_sha")))
