# Copyright (c) 2026, eCentric and contributors
"""Payment Request: vong cho ky het gio thi dung han, khong tu khoi dong lai (review 06/09).

Sau p145, actionPanelHTML goi startSignWait() moi lan ve khi in_flight; het 6 phut ->
refreshDetail -> loadSignReady KHONG ep (khoa khong doi) -> in_flight cu -> startSignWait
lai -> vong 5 giay chay vo han khi mot chan ky ket. Gio het gio: nap readiness co ep, ghi
SIGNWAIT.expiredFor, duong ve khong khoi dong lai, bao "chua xac nhan sau 6 phut".

Patch moi vi p145 (payment_request) da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARK = "SIGNWAIT.expiredFor"


def execute():
    res = page_sync.sync()
    frappe.log_error("p146 payment_request sync=%s" % (res or {}).get("action"), "p146 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p146: trang approvals/payment-request thieu %r sau sync (action=%s)"
                        % (_LANDMARK, (res or {}).get("action")))
