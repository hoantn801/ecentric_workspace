"""Immutable definition for the specialized AI Topup request."""
from dataclasses import dataclass

from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import ExactAndDateFilters, service_callbacks


@dataclass(frozen=True, slots=True)
class AIOptions:
    def __call__(self):
        import frappe
        return {
            "ai_tools": frappe.get_all("EC AI Tool", filters={"is_active": 1},
                fields=["name as value", "tool_name as label", "default_currency"]),
            "currencies": frappe.get_all("Currency", filters={"enabled": 1}, pluck="name"),
            "account_modes": ["Existing Account", "New Account"],
            "request_types": ["New Subscription", "Renewal", "Top-up", "Upgrade"],
            "billing_cycles": ["Monthly", "Quarterly", "Semi-annual", "Annual", "One-time", "Custom"],
        }


AI_TOPUP_DEFINITION = ApprovalDefinition(
    code="AI_TOPUP", business_doctype="EC AI Topup Request", feature="ai_topup",
    editable_fields=("request_title", "account_mode", "ai_account", "ai_tool", "account_email",
        "account_manager", "current_plan", "proposed_account_email", "proposed_account_manager",
        "proposed_plan", "request_type", "requested_plan", "requested_amount", "currency",
        "tax_fee_basis", "needed_by", "purpose", "requester_note", "subscription_start_date",
        "subscription_end_date", "billing_cycle", "auto_renewal_expected", "subscription_start_date"),
    my_request_fields=("name", "request_title", "ai_tool", "account_mode", "account_email",
        "proposed_account_email", "request_type", "requested_amount", "currency", "tax_fee_basis",
        "fulfillment_status", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "ai_tool", "account_mode", "account_email",
        "proposed_account_email", "requested_amount", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS, options_provider=AIOptions(),
    filter_builder=ExactAndDateFilters(("ai_tool", "request_type", "account_mode")),
    **service_callbacks("ai_topup"))


