"""Stateless definition for EC Employee Referral Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)


def _options():
    return {"relationships": ["Friend", "Relative", "Former colleague", "Other"]}


def _submit(name):
    from ecentric_workspace.approval_center.employee_referral.service import submit
    return submit(name)


def _resubmit(name, actor=None):
    from ecentric_workspace.approval_center.employee_referral.service import resubmit
    return resubmit(name, actor=actor)


def _filters(target, supplied):
    if supplied.get("relationship_with_referrer"):
        target["relationship_with_referrer"] = supplied["relationship_with_referrer"]
    if supplied.get("from_date") and supplied.get("to_date"):
        target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


EMPLOYEE_REFERRAL_DEFINITION = ApprovalDefinition(
    code="EMPLOYEE_REFERRAL",
    business_doctype="EC Employee Referral Request",
    editable_fields=("request_title", "candidate_full_name", "candidate_email",
                     "position_applied_for", "hiring_department", "relationship_with_referrer",
                     "relationship_other", "referral_justification", "request_attachment",
                     "department", "company"),
    my_request_fields=("name", "request_title", "candidate_full_name", "position_applied_for",
                       "hiring_department", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "candidate_full_name", "position_applied_for",
                          "hiring_department", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=_options,
    title_builder=None,
    submitter=_submit,
    resubmitter=_resubmit,
    filter_builder=_filters,
)


