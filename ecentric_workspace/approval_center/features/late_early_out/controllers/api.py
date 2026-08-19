# Copyright (c) 2026, eCentric and contributors
"""Stable whitelisted compatibility API for Late/Early Out requests."""
import frappe

from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition


_DEFINITION = get_definition("LATE_EARLY_OUT")
_FACADE = APPROVAL_FACADE
_caps = _FACADE.capabilities
BIZ = _DEFINITION.business_doctype
APPROVAL_TYPE = _DEFINITION.code
MAX_PAGE = _DEFINITION.max_page_length
OPEN = _caps.OPEN_STATUSES
TERMINAL = ("Approved", "Rejected", "Cancelled")
_EDITABLE_DRAFT = _DEFINITION.editable_fields
_STATUS_LABEL = dict(_DEFINITION.status_labels)


def _sm(): return _caps.is_system_manager()
def _employee_ctx(user=None): return _FACADE.employee_context(user)
def _has_any_approver_row(user=None): return _caps.has_any_approver_row(user)
def _req_of(name): return _caps.approval_request_for(_DEFINITION, name)
def _can_view(user, biz, req): return _caps.can_view(user, biz, req)
def _capabilities(user, biz, req): return _caps.derive(user, biz, req)
def _process_preview(code): return _FACADE.process_preview(code)
def _active_level_count(): return len(_FACADE.process_preview(APPROVAL_TYPE))


@frappe.whitelist()
def get_bootstrap():
    return _FACADE.bootstrap(_DEFINITION)


@frappe.whitelist()
def get_form_options():
    return _DEFINITION.options_provider()


@frappe.whitelist()
def list_my_requests(filters=None, start=0, page_length=20):
    return _FACADE.list_my_requests(_DEFINITION, filters, start, page_length)


@frappe.whitelist()
def list_need_my_approval(section="pending"):
    return _FACADE.list_my_approvals(_DEFINITION, section)


list_my_approvals = list_need_my_approval


@frappe.whitelist()
def get_detail(name):
    return _FACADE.detail(_DEFINITION, name)


get_request_detail = get_detail


@frappe.whitelist(methods=["POST"])
def save_draft(name=None, payload=None):
    return _FACADE.save_draft(_DEFINITION, name, payload)


@frappe.whitelist(methods=["POST"])
def submit_request(name):
    return _FACADE.submit(_DEFINITION, name)


def _resolve_req(name): return _FACADE.resolve_request(_DEFINITION, name)


@frappe.whitelist(methods=["POST"])
def approve(name, comment=None):
    return _FACADE.approve(_DEFINITION, name, comment)


@frappe.whitelist(methods=["POST"])
def reject(name, comment=None):
    return _FACADE.reject(_DEFINITION, name, comment)


@frappe.whitelist(methods=["POST"])
def request_information(name, comment=None):
    return _FACADE.request_information(_DEFINITION, name, comment)


@frappe.whitelist(methods=["POST"])
def resubmit(name, payload=None):
    return _FACADE.resubmit(_DEFINITION, name, payload)


@frappe.whitelist(methods=["POST"])
def cancel(name, reason=None):
    return _FACADE.cancel(_DEFINITION, name, reason)


@frappe.whitelist(methods=["POST"])
def admin_approve_current_level(name, reason=None):
    return _FACADE.admin_approve_current_level(_DEFINITION, name, reason)




