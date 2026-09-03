# Copyright (c) 2026, eCentric and contributors
"""Chay lai p134: lan truoc bi khoa chong troi tu choi, trang khong doi mot chu.

p134 chay luc 18:15 va Patch Log ghi la DA CHAY - nhung trang `approvals/hiring-request`
van la ban 01/09. May la p134 co ghi ket qua ra Error Log: `p134 hiring_request sync=refused`.
Khong co dong log do thi chi thay "patch da chay" roi di truy nham cho.

Vi sao refused: `sync()` chi ghi khi ban live bam ra mot trong cac gia tri khai trong
page_sync.py (khoa chong troi #144, de mot lenh sync lac khong am tham ghi de ban ai do sua
tay tren site). p118 (XSS steppers) da ghi trang nay nhung KHONG cap nhat hai hang so do,
nen ban live troi khoi moi gia tri duoc chap nhan.

Sua bang cach DO chu khong doan: bam `main_section_html` tren production ra
`2f178787d99aa87fdda714e3811bfd2dc256565898c2b8ca3615e8326d32a90b` roi them dung gia tri do
vao SUPERSEDES_SHA256. KHONG dung force=1 - force go bo han khoa, tuc lan sau ai sua tay
tren site se bi ghi de im lang; them mot gia tri da do duoc thi khoa van lam viec cua no.

Patch moi vi p134 da chay - patch chay MOT LAN, va mot patch da chay thi khong bao gio chay
lai du no khong lam duoc gi.
"""
import frappe

from ecentric_workspace.approval_center.features.hiring_request.infrastructure import page_sync


def execute():
    res = page_sync.sync() or {}
    action = res.get("action")
    frappe.log_error("p135 hiring_request sync=%s" % action, "p135 resync")
    print("[OK] hiring_request sync=%s" % action)

    # VERIFY - doc lai tu DB, khong tin gia tri tra ve.
    name = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "name")
    html = frappe.db.get_value("Web Page", name, "main_section_html") or "" if name else ""
    con_doctype = 'append("doctype"' in html or "append('doctype'" in html
    print("[OK]  trang khong con gui doctype" if not con_doctype
          else "[ERR] trang VAN gui doctype - sync khong an")
    if con_doctype:
        frappe.throw("p135: trang hiring-request van gui doctype kem upload_file (action=%s)"
                     % action)
