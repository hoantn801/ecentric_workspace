# Copyright (c) 2026, eCentric and contributors
"""Resync hub /approvals/all-requests: bao thong diep THAT cua may chu khi duyet tu hub.

Hoan ghi nhan 02/09: bam Duyet tu hub (ngoai form) khi cap yeu cau ky so -> chi thay
"Khong thuc hien duoc." / ma tho, phai mo form moi biet vi sao. Hai cho trong hub doc
`e.message` - rong voi frappe.throw, thong diep nam o `_server_messages`. p123/p126 da sua
dung loi nay cho 7 form nhung bo sot hub. Gio hub dung cung extractServerMsg.

Patch moi vi p125 (resync hub gan nhat) da chay - patch chay MOT LAN.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p131 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p131 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p131 resync failed")
        raise
