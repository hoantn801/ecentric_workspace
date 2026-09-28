# Copyright (c) 2026, eCentric and contributors
"""Loc `frappe.response.docinfo.versions` ngay sau khi Frappe dung xong docinfo.

Goi tu ba endpoint bi ghi de (xem form_load.py). Loi bat ky -> xoa sach danh sach Version
cua lan tai do (dong cua), ghi Error Log - tuyet doi khong de form sap vi bo loc.
"""
import frappe

from ecentric_workspace.hr.privacy import permlevels
from ecentric_workspace.hr.privacy.version_filter import filter_versions


def scrub_response_versions():
    docinfo = frappe.response.get("docinfo")
    if not docinfo or not docinfo.get("versions"):
        return
    if frappe.session.user == "Administrator":
        return
    try:
        doctype = docinfo.get("doctype")
        if not permlevels.needs_filter(doctype):
            return
        readable, children = permlevels.readable_fields(doctype)
        docinfo["versions"] = filter_versions(docinfo["versions"], readable, children)
    except Exception:
        docinfo["versions"] = []
        frappe.log_error(title="EC: loc lich su thay doi theo permlevel that bai")
