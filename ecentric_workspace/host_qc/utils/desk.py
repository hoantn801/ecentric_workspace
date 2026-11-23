# Copyright (c) 2026, eCentric and contributors
"""Cau noi controller DocType -> service: loi nghiep vu hien thanh thong bao tren form (frappe.throw),
khong de traceback "Server Error" lot ra Desk."""
import frappe

from ecentric_workspace.host_qc.exceptions import HostQCError


def run(service, doc):
    try:
        service.execute(doc)
    except HostQCError as e:
        frappe.throw(str(e), title="Host QC")
