# Copyright (c) 2026, eCentric and contributors
"""Hai loi Hoan bao 04/09 sang, ngay sau p137:

1. Trinh dat vi tri ky: dai ~58px ben phai trang PDF khong dat/keo o vao duoc (da bao 28/08,
   lai bao 04/09). Do tren prod: #ecdStage x=676 w=727 (block), #ecdCanvas x=734 w=612,
   #ecdLayer x=676 w=612. Nguyen nhan: `stage.style.display = canPdf ? "" : "none"` - gan ""
   la XOA inline `display:inline-block`, div ve `block` rong ca khung, canvas bi
   text-align:center day sang phai 58px, overlay van bam mep trai. Sua: "inline-block".
   (document_signing_section.html)

2. Phieu CHUA GUI khong hien o "Ket noi tai khoan ky so SCTS" - vi `approval_type` trong o
   ban nhap nen readiness pre-submit bao requester_signature_required=false va panel an.
   Nguoi dung chi biet minh chua ket noi luc bam Gui. Sua: khi doctype chi co DUNG MOT
   profile ky so dang bat thi lay loai yeu cau cua profile do (requester._draft_approval_type).
   Phan nay la Python, khong can resync; patch nay chi dong bo lai trang cho loi 1.

Patch moi vi p137 da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARK = 'style.display = canPdf ? "inline-block" : "none"'


def execute():
    res = page_sync.sync()
    frappe.log_error("p139 payment_request sync=%s" % (res or {}).get("action"), "p139 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p139: trang approvals/payment-request van chua co sua stage "
                        "inline-block sau sync (action=%s)" % (res or {}).get("action"))
