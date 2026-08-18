"""Build whitelisted functions for vertical business modules.

The returned functions are installed as attributes of each legacy API module, so
Frappe dotted paths remain unchanged while behavior is owned by the application layer.
"""
import frappe

from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition


def bind(approval_code):
    definition = get_definition(approval_code)
    facade = APPROVAL_FACADE
    caps = facade.capabilities

    @frappe.whitelist()
    def get_bootstrap():
        return facade.bootstrap(definition)

    @frappe.whitelist()
    def get_form_options():
        return facade.options(definition)

    @frappe.whitelist()
    def list_my_requests(filters=None, start=0, page_length=20):
        return facade.list_my_requests(definition, filters, start, page_length)

    @frappe.whitelist()
    def list_need_my_approval(section="pending"):
        return facade.list_my_approvals(definition, section)

    @frappe.whitelist()
    def get_detail(name):
        return facade.detail(definition, name)

    @frappe.whitelist(methods=["POST"])
    def save_draft(name=None, payload=None):
        return facade.save_draft(definition, name, payload)

    @frappe.whitelist(methods=["POST"])
    def submit_request(name):
        return facade.submit(definition, name)

    @frappe.whitelist(methods=["POST"])
    def approve(name, comment=None):
        return facade.approve(definition, name, comment)

    @frappe.whitelist(methods=["POST"])
    def reject(name, comment=None):
        return facade.reject(definition, name, comment)

    @frappe.whitelist(methods=["POST"])
    def request_information(name, comment=None):
        return facade.request_information(definition, name, comment)

    @frappe.whitelist(methods=["POST"])
    def resubmit(name, payload=None):
        return facade.resubmit(definition, name, payload)

    @frappe.whitelist(methods=["POST"])
    def cancel(name, reason=None):
        return facade.cancel(definition, name, reason)

    @frappe.whitelist(methods=["POST"])
    def admin_approve_current_level(name, reason=None):
        return facade.admin_approve_current_level(definition, name, reason)

    def _sm():
        return caps.is_system_manager()

    def _employee_ctx(user=None):
        return facade.employee_context(user)

    def _has_any_approver_row(user=None):
        return caps.has_any_approver_row(user)

    def _req_of(name):
        return caps.approval_request_for(definition, name)

    def _can_view(user, business, request):
        return caps.can_view(user, business, request)

    def _capabilities(user, business, request):
        return caps.derive(user, business, request)

    def _process_preview(code):
        return facade.process_preview(code)

    def _active_level_count():
        return len(facade.process_preview(definition.code))

    def _resolve_req(name):
        return facade.resolve_request(definition, name)

    return {
        "_DEFINITION": definition,
        "BIZ": definition.business_doctype,
        "APPROVAL_TYPE": definition.code,
        "MAX_PAGE": definition.max_page_length,
        "OPEN": caps.OPEN_STATUSES,
        "TERMINAL": ("Approved", "Rejected", "Cancelled"),
        "_EDITABLE_DRAFT": definition.editable_fields,
        "_STATUS_LABEL": dict(definition.status_labels),
        "_sm": _sm,
        "_employee_ctx": _employee_ctx,
        "_has_any_approver_row": _has_any_approver_row,
        "_req_of": _req_of,
        "_can_view": _can_view,
        "_capabilities": _capabilities,
        "_process_preview": _process_preview,
        "_active_level_count": _active_level_count,
        "_resolve_req": _resolve_req,
        "get_bootstrap": get_bootstrap,
        "get_form_options": get_form_options,
        "list_my_requests": list_my_requests,
        "list_need_my_approval": list_need_my_approval,
        "list_my_approvals": list_need_my_approval,
        "get_detail": get_detail,
        "get_request_detail": get_detail,
        "save_draft": save_draft,
        "submit_request": submit_request,
        "approve": approve,
        "reject": reject,
        "request_information": request_information,
        "resubmit": resubmit,
        "cancel": cancel,
        "admin_approve_current_level": admin_approve_current_level,
    }
