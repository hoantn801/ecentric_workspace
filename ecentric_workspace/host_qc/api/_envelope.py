# Copyright (c) 2026, eCentric and contributors
"""Boc ket qua thanh {success, message, data} + ma HTTP.

App AI Host QC chi thu lai khi 5xx / 408 / 429, nen: loi du lieu / quyen -> 4xx (khong thu lai), loi tam
cua ERP (DB khoa, loi khong luong truoc) -> 503 de may giu ban ghi va gui lai. Khong de traceback lot ra."""
import frappe

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.exceptions import HostQCError

TEMP_ERROR_STATUS = 503


def _fail(status, message, data=None):
    frappe.db.rollback()
    frappe.local.response["http_status_code"] = status
    return {"success": False, "message": message, "data": data}


def run(fn, message=""):
    try:
        return {"success": True, "message": message, "data": fn()}
    except HostQCError as e:
        return _fail(e.http_status, str(e) or M.UNKNOWN, e.data)
    except frappe.ValidationError as e:
        return _fail(HostQCError.http_status, frappe.utils.strip_html(str(e)) or M.UNKNOWN)
    except Exception:
        frappe.log_error(title="host_qc api")
        return _fail(TEMP_ERROR_STATUS, M.UNKNOWN)
