"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentRows, ExactAndDateFilters, StaticOptions, service_callbacks,
)


def _make(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, feature=feature, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters), **service_callbacks(feature))

SYSTEM_REQUEST_DEFINITION = _make(
    "SYSTEM_REQUEST", "EC System Request", "system_request",
    ("request_title", "request_type", "other_type", "description", "priority",
     "requester_expected_resolution_date", "request_attachment", "department", "company"),
    ("name", "request_title", "request_type", "priority", "requester_expected_resolution_date",
     "operation_expected_completion_date", "fulfillment_status", "approval_request", "creation", "modified"),
    ("name", "request_title", "request_type", "priority", "requester_expected_resolution_date",
     "fulfillment_status", "department", "creation"),
    StaticOptions((("request_types", ("License, account", "Access, permission", "Initiative, solution",
       "Lark Approvals", "Other")), ("priorities", ("Low", "Normal", "High", "Urgent")))),
    ("request_type",))



