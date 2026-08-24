# Copyright (c) 2026, eCentric and contributors
"""Cross-form actions for the 'Tất cả yêu cầu' hub.

The per-form pages expose approve/reject/claim under their own namespace
(ecentric_workspace.approval_center.api.<form>.*), which the hub cannot use because it
lists every form at once. This module resolves the form from the request itself
(EC Approval Request.approval_type -> registry definition) and delegates to the SAME
facade the form pages use, so authority, transitions and audit are unchanged -- this is a
router, never a second implementation of the rules.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition


def _resolve(request_name):
    """EC Approval Request name -> (definition, business_name)."""
    row = frappe.db.get_value("EC Approval Request", request_name,
                              ["approval_type", "reference_doctype", "reference_name"], as_dict=True)
    if not row or not row.approval_type or not row.reference_name:
        frappe.throw(_("Không tìm thấy yêu cầu."), frappe.DoesNotExistError)
    try:
        definition = get_definition(row.approval_type)
    except KeyError:
        frappe.throw(_("Loại yêu cầu {0} chưa được đăng ký.").format(row.approval_type))
    return definition, row.reference_name


@frappe.whitelist(methods=["POST"])
def approve(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.approve(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def reject(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.reject(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def request_information(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.request_information(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(request_name):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.claim_fulfillment(definition, name)
