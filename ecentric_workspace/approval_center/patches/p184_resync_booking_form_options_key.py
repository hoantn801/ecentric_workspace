# Copyright (c) 2026, eCentric and contributors
"""Booking Request: o Brand bao "danh muc trong" trong khi he thong co 28 brand (14/09).

DO TREN PRODUCTION ngay sau khi bat form: goi thang
`api.booking_request.get_bootstrap` tra ve DU 28 brand, nhung man hinh van hien
"Danh muc brand dang trong". Tuc server dung, man hinh sai.

Goc: `get_bootstrap` tra khoa **form_options**, ma UI doc `state.boot.options`. Mot chu
sai, khong loi, khong canh bao - chi la mot danh sach rong. Hau qua that: nguoi dung se GO
TAY ten brand da co san, sinh ra brand trung trong danh muc, dung cai viec form nay sinh ra
de tranh.

Sua: doc `form_options`, van chap nhan `options` de khong gay hoi quy neu ban sau doi lai.

Landmark = dieu PHAI CO tren ban song."""
import frappe

from ecentric_workspace.approval_center.features.booking_request.infrastructure import page_sync

_LANDMARKS = ("form_options",)


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p184 booking-request sync=%s" % action, "p184 resync")
    if action == "refused":
        frappe.log_error("p184: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p184 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/booking-request"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p184: trang booking-request thieu dau moc %s" % thieu,
                         "p184 KHONG toi noi")
