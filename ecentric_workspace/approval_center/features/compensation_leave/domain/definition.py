"""Stateless definition for EC Compensation Leave Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


def _options():
    return {}


def _title(doc):
    from ecentric_workspace.approval_center.features.compensation_leave.application.service import gen_title
    return gen_title(doc)


def _submit(name):
    from ecentric_workspace.approval_center.features.compensation_leave.application.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.features.compensation_leave.application.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("cl_start_date"):
        target["cl_start_date"] = supplied["cl_start_date"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


COMPENSATION_LEAVE_DEFINITION = ApprovalDefinition(
    code="COMPENSATION_LEAVE",
    business_doctype="EC Compensation Leave Request",
    editable_fields=("overtime_start_date", "overtime_end_date", "overtime_duration_days",
                     "cl_start_date", "cl_end_date", "cl_duration_days", "remarks",
                     "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "cl_start_date", "cl_end_date", "cl_duration_days",
                       "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "cl_start_date", "cl_end_date",
                          "cl_duration_days", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=_title,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


