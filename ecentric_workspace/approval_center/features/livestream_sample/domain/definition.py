"""Stateless definition for EC Livestream Sample Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


def _options():
    return {}


def _submit(name):
    from ecentric_workspace.approval_center.features.livestream_sample.application.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.features.livestream_sample.application.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("brand"):
        target["brand"] = ["like", "%%%s%%" % supplied["brand"]]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


LIVESTREAM_SAMPLE_DEFINITION = ApprovalDefinition(
    code="LIVESTREAM_SAMPLE",
    business_doctype="EC Livestream Sample Request",
    editable_fields=("request_title", "brand", "sample_detail", "estimated_arrival_time",
                     "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "brand", "estimated_arrival_time",
                       "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "brand", "estimated_arrival_time",
                          "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=None,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


