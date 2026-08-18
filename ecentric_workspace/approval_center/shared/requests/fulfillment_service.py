"""Shared application service for request-type fulfillment endpoints."""
import frappe

from ecentric_workspace.approval_center.shared.workflow.permissions import is_eligible_fulfiller


def list_queue(definition, section, fields, order_by):
    user = frappe.session.user
    if not is_eligible_fulfiller(user, approval_type=definition.code,
                                 business_doctype=definition.business_doctype):
        return {"rows": []}
    if section == "unclaimed":
        filters = {"fulfillment_status": "Assigned"}
    elif section == "mine":
        filters = {"fulfillment_owner": user,
                   "fulfillment_status": ["in", ["Assigned", "In Progress"]]}
    else:
        filters = {"fulfillment_status": "In Progress", "fulfillment_owner": ["!=", user]}
    return {"rows": frappe.get_all(
        definition.business_doctype, filters=filters, fields=list(fields),
        order_by=order_by, limit_page_length=200)}


def claim(definition, name):
    service = __import__(
        "ecentric_workspace.approval_center.%s.service" % definition.feature,
        fromlist=["claim_fulfillment"])
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        result = service.claim_fulfillment(name)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return result


def complete(definition, name, payload=None):
    service = __import__(
        "ecentric_workspace.approval_center.%s.service" % definition.feature,
        fromlist=["complete_fulfillment"])
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        service.complete_fulfillment(name, payload=payload)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []




