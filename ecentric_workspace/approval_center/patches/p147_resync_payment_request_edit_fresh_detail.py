# Copyright (c) 2026, eCentric and contributors
"""Payment Request: form sua ban nhap nap ban chi tiet MOI; khoi ky so bao sau khi tai (07/09).

p146 da chay tren prod (12:51) voi ban HTML TRUOC khi them sua nay; toi ghi de landmark vao
p146 ma quen luat "patch chay MOT LAN" -> HTML moi khong bao gio len. Patch moi, tu VERIFY.

Noi dung: startEditDraft nap get_detail moi (request_attachment do khoi ky so dat len server
sau khi form nap); document_signing_section phat payr:attachments-changed sau khi tai xong;
form dang mo cap nhat con tro. Het canh "da tai tep ma Gui van bao thieu tep".
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("function _startEditDraftWith", "function _announce()")


def execute():
    res = page_sync.sync()
    frappe.log_error("p147 payment_request sync=%s" % (res or {}).get("action"), "p147 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p147: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
