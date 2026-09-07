# Copyright (c) 2026, eCentric and contributors
"""Payment Request: khoi "Ke hoach chia dot" giu focus khi ve lai; dot 1 > tong bao vuot (08/09).

Hoan: "cu nhap 1 so vao la phai click lai moi nhap duoc so tiep theo" - o Tong gia tri nam TRONG
khoi, moi phim thay ca khoi -> mat o dang go. Nay nho data-model + con tro roi tra lai. Va
"nhap dot 1 lon hon tong thi sao": truoc hien "0d / 0d" + "dot cuoi" (sai), nay bao do
"vuot phan con lai cua tong gia tri". Patch moi vi p155 da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("focusKey", "vượt phần còn lại của tổng giá trị")


def execute():
    res = page_sync.sync()
    frappe.log_error("p156 payment_request sync=%s" % (res or {}).get("action"), "p156 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p156: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
