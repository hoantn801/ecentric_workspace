# Copyright (c) 2026, eCentric and contributors
"""Payment Request: tep ky mat tren dia khong duoc giet khoi "Tai lieu & ky so" (08/09, 00046).

Ban ghi File SIGNED-...DNTT.pdf con, file tren dia mat -> document_setup_state nem
FileNotFoundError -> ca khoi 500. Nay dong do bao "tep khong con tren may chu", cac dong khac
van hien (document_signing_section). Kem: o tien data-model nguyen van (cong QC), API SM
restore_missing_signed_files (tai lai tu SCTS, doi chieu SHA, ghi dung duong dan cu).
Patch moi vi p157 da chay. Tu VERIFY landmark tren trang payment-request (khoi ky so duoc
page_sync ghep vao cung trang).
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("d.file_missing", "function moneyInputHTML(attrs, value)")


def execute():
    res = page_sync.sync()
    frappe.log_error("p158 payment_request sync=%s" % (res or {}).get("action"), "p158 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p158: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
