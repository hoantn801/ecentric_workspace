# Copyright (c) 2026, eCentric and contributors
"""Resync trang van hanh ky so: them nut "Gui lai co kiem" (authorize_resend).

Chan ky da tung gui ma SCTS khong tao chu ky (00042/DSR-00027, 02/09) chi co the quay ve
Manual Review mai mai - Thu lai KHONG gui lai (dung y). Nut moi chi hien khi Thu lai khong
gui lai duoc; may chu hoi SCTS va tu choi neu nguoi do da co chu ky. Patch moi vi p122
(resync ops gan nhat) da chay - patch chay MOT LAN.
"""
import frappe

from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    try:
        frappe.log_error("p132 ops sync=%s" % (ops_page_sync.sync() or {}).get("action"),
                         "p132 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p132 resync failed")
        raise
