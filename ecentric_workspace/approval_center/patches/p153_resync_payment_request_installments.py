# Copyright (c) 2026, eCentric and contributors
"""Payment Request: thanh toan chia dot (07/09, Hoan).

Moi dot = mot phieu rieng (duyet + 5 chu ky rieng). Form: Hinh thuc (100% / Chia dot), Tong
gia tri, so tien dot nay, dot ke tu tinh + ngay du kien; chi tiet: chuoi cac dot tren dau
tien trinh, the "Thanh toan chia dot", nut "Tao de nghi dot k+1" (clone phieu dot truoc sau
khi da chi UNC), gap 6 buoc khi dot da xong va co dot ke. Backend: service.validate_installment
/ installments_block / create_next_installment, reminders.remind_next_installment (D-7).
Patch moi vi p150 da chay tren prod. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("function instChainHTML(det)", "function doNextInstallment(name)",
              'data-model="payment_mode"')


def execute():
    res = page_sync.sync()
    frappe.log_error("p153 payment_request sync=%s" % (res or {}).get("action"), "p153 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p153: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
