# Copyright (c) 2026, eCentric and contributors
"""Resync trang /approvals/employee-information-update (29/09/2026): o "Field to update" lay
danh sach tu ho so nhan vien (server), dien san gia tri hien tai, o "New value" theo kieu
truong, bang ket qua ghi ho so o chi tiet. Schema doi (field_to_update Select -> Data, them
target_employee / applied_at / apply_result) do bench migrate tu lam. Khong nem loi."""
import frappe

PAGE = "ecentric_workspace.approval_center.features.employee_info_update.infrastructure.page_sync"


def execute():
    try:
        res = frappe.get_module(PAGE).sync() or {}
        msg = "employee_info_update: %s" % res.get("action")
    except Exception:
        msg = "employee_info_update: LOI\n" + frappe.get_traceback()
    frappe.log_error(title="p232 eiu ho so nhan vien", message=msg)
