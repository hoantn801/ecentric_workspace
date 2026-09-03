# Copyright (c) 2026, eCentric and contributors
"""Form Tuyen dung: nguoi de nghi khong dinh kem duoc tep - cung loi voi khoi ky so (p133).

`uploadAttachment` gui `doctype`+`docname` kem `/api/method/upload_file`. Endpoint do la cua
Frappe va kiem quyen bang DocPerm CHUAN; `EC Hiring Request` chi co MOT dong DocPerm cho
System Manager, khong dong nao cho Employee. Va day KHONG phai o cua nguoi xu ly - day la o
dinh kem cua chinh NGUOI DE NGHI (`wireFile` -> `uploadAttachment` -> `request_attachment`).

Bang chung no chua bao gio chay: tren production khong co MOT tep nao dinh vao
`EC Hiring Request`, trong khi Daily Target va HR Activity - hai form tai len KHONG kem
doctype - co 17 tep cua nhan vien thuong.

Tim ra nho phep kiem trong test_upload_no_doctype_permission.py, khong phai nho doc code:
grep tay cua toi hep hon regex cua test nen bo sot 6 trang, day la mot trong so do.

Sua giong 13 form khac: tai len KHONG kem doctype/docname (tep rieng tu, chua thuoc ho so
nao), URL gan vao truong `request_attachment`, backend gan tep vao phieu khi luu.

Patch moi vi p028 (tao trang) da chay tu lau - patch chay MOT LAN.
"""
import frappe

from ecentric_workspace.approval_center.features.hiring_request.infrastructure import page_sync


def execute():
    try:
        frappe.log_error("p134 hiring_request sync=%s" % (page_sync.sync() or {}).get("action"),
                         "p134 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p134 resync failed")
        raise
