# Copyright (c) 2026, eCentric and contributors
"""Payment Request: "dang cho nha cung cap xac nhan" phai SONG SOT khi tai lai trang (06/09).

Chi Lien bam "Duyet & Ky" tren 00043 roi Ctrl+Shift+R: khu Hanh dong hien lai "Duyet & Ky /
Yeu cau bo sung / Tu choi" nhu chua bam. Trang thai cho truoc day chi nam trong bien JS
(SIGNWAIT). Gio signing_readiness tra `in_flight` (chan ky dang bay cua chinh nguoi nay o cap
nay, doc tu DSR); man hinh doc no de an nut, bao dang cho, va tu poll tiep.

Patch moi vi p144 (payment_request) da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARK = "state._signReady.in_flight"


def execute():
    res = page_sync.sync()
    frappe.log_error("p145 payment_request sync=%s" % (res or {}).get("action"), "p145 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p145: trang approvals/payment-request thieu %r sau sync (action=%s)"
                        % (_LANDMARK, (res or {}).get("action")))
