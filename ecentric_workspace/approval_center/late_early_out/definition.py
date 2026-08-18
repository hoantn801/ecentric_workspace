"""Stateless definition for EC Late Early Out Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


CHECK_TIMES = ("10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "Other")


def _options():
    return {"check_times": list(CHECK_TIMES)}


def _title(doc):
    from ecentric_workspace.approval_center.late_early_out.service import gen_title
    return gen_title(doc)


def _submit(name):
    from ecentric_workspace.approval_center.late_early_out.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.late_early_out.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("check_time"):
        target["check_time"] = supplied["check_time"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


LATE_EARLY_OUT_DEFINITION = ApprovalDefinition(
    code="LATE_EARLY_OUT",
    business_doctype="EC Late Early Out Request",
    editable_fields=("request_type", "applied_date", "check_time", "check_time_other", "reason",
                     "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "request_type", "applied_date", "check_time",
                       "check_time_other", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "request_type", "applied_date", "check_time",
                          "check_time_other", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=_title,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


