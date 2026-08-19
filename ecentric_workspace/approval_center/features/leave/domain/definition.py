"""Stateless definition for EC Leave Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


LEAVE_TYPES = ("Annual", "Sick", "Errand", "Maternity", "Paternity", "Marriage", "Bereavement")


def _options():
    return {"leave_types": list(LEAVE_TYPES)}


def _title(doc):
    from ecentric_workspace.approval_center.features.leave.application.service import gen_title
    return gen_title(doc)


def _submit(name):
    from ecentric_workspace.approval_center.features.leave.application.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.features.leave.application.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("leave_type"):
        target["leave_type"] = supplied["leave_type"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


LEAVE_DEFINITION = ApprovalDefinition(
    code="LEAVE_REQUEST",
    business_doctype="EC Leave Request",
    editable_fields=("leave_type", "start_date", "end_date", "duration_days", "remarks",
                     "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "leave_type", "start_date", "end_date",
                       "duration_days", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "leave_type", "start_date", "end_date",
                          "duration_days", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=_title,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


