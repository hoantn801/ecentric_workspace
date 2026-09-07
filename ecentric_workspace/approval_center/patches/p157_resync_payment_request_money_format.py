# Copyright (c) 2026, eCentric and contributors
"""Payment Request: o tien hien dau cham ngan cach hang nghin (08/09, Hoan: "kho doc qua").

<input type=number> khong cho dau phan cach -> o tien (so tien dot nay, tong gia tri, dot ke)
thanh type=text inputmode=numeric data-money: hien "323.001.802", model giu SO (chi lay chu
so, khong parseFloat chuoi vi-VN), giu con tro khi dinh dang lai. Patch moi vi p156 da chay.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("function reformatMoneyInput(el)", 'data-money="1"')


def execute():
    res = page_sync.sync()
    frappe.log_error("p157 payment_request sync=%s" % (res or {}).get("action"), "p157 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p157: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
