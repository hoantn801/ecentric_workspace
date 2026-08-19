"""Build fulfillment endpoints shared by operational business modules."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition


def bind_fulfillment(code, queue_fields, order_by, operation_fields=False):
    definition = get_definition(code)
    endpoints = bind(code)
    facade = APPROVAL_FACADE

    @frappe.whitelist()
    def list_fulfillment_queue(section="unclaimed"):
        return facade.list_fulfillment_queue(
            definition, section, queue_fields, order_by)

    @frappe.whitelist(methods=["POST"])
    def claim_fulfillment(name):
        result = facade.claim_fulfillment(definition, name)
        return {"claimed": True, "owner": result.get("owner"),
                "detail": endpoints["get_detail"](name)}

    @frappe.whitelist(methods=["POST"])
    def complete_fulfillment(name, payload=None):
        facade.complete_fulfillment(definition, name, payload)
        return {"completed": True, "detail": endpoints["get_detail"](name)}

    endpoints.update({
        "list_fulfillment_queue": list_fulfillment_queue,
        "claim_fulfillment": claim_fulfillment,
        "complete_fulfillment": complete_fulfillment,
    })
    if operation_fields:
        @frappe.whitelist(methods=["POST"])
        def approve(name, comment=None, operation_expected_completion_date=None):
            return facade.approve_with_operation_date(
                definition, name, comment, operation_expected_completion_date)

        @frappe.whitelist(methods=["POST"])
        def set_operation_fields(name, operation_expected_completion_date=None, operation_note=None):
            service = __import__(
                "ecentric_workspace.approval_center.features.%s.application.service" % definition.feature,
                fromlist=["set_operation_fields"])
            service.set_operation_fields(
                name, operation_expected_completion_date=operation_expected_completion_date,
                operation_note=operation_note)
            return {"ok": True, "detail": endpoints["get_detail"](name)}
        endpoints["set_operation_fields"] = set_operation_fields
        endpoints["approve"] = approve
    return endpoints

