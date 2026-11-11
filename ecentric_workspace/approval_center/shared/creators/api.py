# Copyright (c) 2026, eCentric and contributors
"""Transport cho creator master. Chi parse tham so, goi service, doi loi sang frappe.throw.

Duong dan cong khai: ecentric_workspace.approval_center.api.creators.<ham>.
"""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.creators import import_service
from ecentric_workspace.approval_center.shared.creators.service import (
    CreatorError, CreatorPermissionError, CreatorService)


def _payload(data):
    if isinstance(data, str):
        data = json.loads(data or "{}")
    if not isinstance(data, dict):
        frappe.throw(_("Dữ liệu creator không hợp lệ."))
    return data


def _run(fn, *args):
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập."), frappe.PermissionError)
    try:
        return fn(frappe.session.user, *args)
    except CreatorPermissionError as e:
        frappe.throw(_(str(e)), frappe.PermissionError)
    except CreatorError as e:
        frappe.throw(_(str(e)))


@frappe.whitelist()
def search_creators(query=None, limit=None):
    return _run(CreatorService().search, query, limit)


@frappe.whitelist()
def get_creator(name):
    return _run(CreatorService().get, name)


@frappe.whitelist(methods=["POST"])
def create_creator(data, confirm_soft=0):
    return _run(CreatorService().create, _payload(data), str(confirm_soft) in ("1", "true"))


@frappe.whitelist(methods=["POST"])
def update_creator(name, data):
    return _run(CreatorService().update, name, _payload(data))


@frappe.whitelist()
def list_missing_misa():
    return _run(CreatorService().missing_misa)


@frappe.whitelist(methods=["POST"])
def set_misa_code(name, code):
    return _run(CreatorService().set_misa_code, name, code)


@frappe.whitelist(methods=["POST"])
def import_creators(rows, apply=0):
    """Nhap creator tu sheet cu. Mac dinh chay thu; apply=1 moi ghi. Chi EC Finance."""
    if isinstance(rows, str):
        rows = json.loads(rows or "[]")
    if not isinstance(rows, list):
        frappe.throw(_("Danh sách dòng không hợp lệ."))
    do_apply = str(apply) in ("1", "true")
    return _run(lambda user: import_service.import_rows(user, rows, apply=do_apply))
