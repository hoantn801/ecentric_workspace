"""Stateless definition for EC Asset Damage/Loss Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


def _options():
    return {
        "asset_types": ["Laptop", "Desktop computer", "Monitor", "Mobile device",
                        "Printer", "RAM", "Other"],
        "incident_types": ["Damage", "Loss", "Theft", "Other"],
        "recommended_actions": ["Repair", "Replace", "Write-off",
                                "Further investigation", "Other"],
    }


def _submit(name):
    from ecentric_workspace.approval_center.features.asset_damage_loss.application.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.features.asset_damage_loss.application.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("incident_type"):
        target["incident_type"] = supplied["incident_type"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


ASSET_DAMAGE_LOSS_DEFINITION = ApprovalDefinition(
    code="ASSET_DAMAGE_LOSS",
    business_doctype="EC Asset Damage Loss Request",
    editable_fields=("request_title", "asset_type", "asset_type_other", "asset_code",
                     "incident_type", "incident_type_other", "incident_description",
                     "incident_date", "incident_location", "witnesses", "physical_damage",
                     "data_compromised", "impact_on_operations", "estimated_repair_cost",
                     "estimated_value_lost_stolen_asset", "recommended_actions",
                     "recommended_actions_other", "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "asset_type", "incident_type", "incident_date",
                       "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "asset_type", "incident_type", "incident_date",
                          "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=None,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


