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

DATA_REQUEST_DEFINITION = _make(
    "DATA_REQUEST", "EC Data Request", "data_request",
    ("request_title", "request_type", "detailed_description", "expected_resolution_date",
     "urgency", "importance", "request_attachment", "department", "company"),
    ("name", "request_title", "request_type", "urgency", "importance", "expected_resolution_date",
     "fulfillment_status", "approval_request", "creation", "modified"),
    ("name", "request_title", "request_type", "urgency", "importance", "expected_resolution_date",
     "department", "creation"),
    StaticOptions((("request_types", ("Data accuracy, visualization, retrieval", "Client onboarding",
       "Client offboarding", "Historical data crawling", "New BI report", "Data training", "Access", "Other")),
       ("urgencies", ("U0: as soon as possible", "U1: within next 24 hours", "U2: within next 3 days",
                      "U3: non-urgent / nice to have")),
       ("importances", ("I0: large-scale impact, critical customer request, critical data loss or corruption",
          "I1: major impact to >2 customers, any major data loss or corruption",
          "I2: minor impact to >2 customers, possible workaround",
          "I3: known bug, little impact, single customer issue")))), ("request_type",))



