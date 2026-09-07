# Copyright (c) 2026, eCentric and contributors
"""Payment Request: trinh bay lai form chia dot (08/09, Hoan: "form trong hoi lon xon").

Truoc: cac o Tong gia tri / dot ke xen vao luoi 2 cot cua "Thong tin thanh toan", de lai o
trong. Nay: cac o thanh toan giu vi tri co dinh (100% hay chia dot deu nhu nhau), khoi
"Ke hoach chia dot" la mot khung rieng full-width duoi Ly do (tong, da de nghi / con lai,
so tien + ngay du kien dot ke). Nhan hinh thuc noi ro "chia NHIEU dot" (khong gioi han so dot).
Patch moi vi p153 da chay tren prod. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("function installmentPlanHTML(d)", 'id="payr-inst-plan"')


def execute():
    res = page_sync.sync()
    frappe.log_error("p155 payment_request sync=%s" % (res or {}).get("action"), "p155 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p155: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
