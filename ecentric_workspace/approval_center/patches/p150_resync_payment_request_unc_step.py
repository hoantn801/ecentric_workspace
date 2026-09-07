# Copyright (c) 2026, eCentric and contributors
"""Payment Request: buoc 6 "Finance xu ly UNC" tren form (07/09, Hoan).

Preview quy trinh 6 buoc; stepper runtime doc det.fulfillment (Cho nhan / Dang xu ly / Da UNC /
khong ap dung cho phieu cu); the "Xu ly UNC (Finance)" voi Nhan xu ly, tai file UNC + Hoan tat;
stepLabel N = cap duyet + 3. Backend: service.on_final_approval/claim/complete + p149 (Fulfiller
Role EC Finance) + scheduler remind_unc_due.
Patch moi vi p147 da chay tren prod. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("function uncSectionHTML(det)", "function doUncComplete(name)", 'data-act="unc-claim"')


def execute():
    res = page_sync.sync()
    frappe.log_error("p150 payment_request sync=%s" % (res or {}).get("action"), "p150 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p150: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
