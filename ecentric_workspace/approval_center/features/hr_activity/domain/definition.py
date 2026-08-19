"""Stateless definition for EC HR Activity Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


def _options():
    return {"activity_types": ["Double day", "Quarterly team bonding",
            "Holiday and anniversary", "Company trip", "Year-end party",
            "Medical checkup", "Monthly L&D", "Other"]}


def _submit(name):
    from ecentric_workspace.approval_center.features.hr_activity.application.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.features.hr_activity.application.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("activity_type"):
        target["activity_type"] = supplied["activity_type"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


HR_ACTIVITY_DEFINITION = ApprovalDefinition(
    code="HR_ACTIVITY",
    business_doctype="EC HR Activity Request",
    editable_fields=("request_title", "activity_type", "activity_type_other", "detail",
                     "start_date", "end_date", "participants", "justification",
                     "estimated_budget", "vendor_trainer_partner_info", "request_attachment",
                     "department", "company"),
    my_request_fields=("name", "request_title", "activity_type", "start_date", "end_date",
                       "estimated_budget", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "activity_type", "start_date", "end_date",
                          "estimated_budget", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=None,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


