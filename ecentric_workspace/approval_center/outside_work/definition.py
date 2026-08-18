"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    StaticOptions,
    service_callbacks,
)


def _definition(code, doctype, feature, editable, mine, approvals, options=(), filters=(), title=False):
    return ApprovalDefinition(
        code=code,
        business_doctype=doctype,
        editable_fields=editable,
        my_request_fields=mine,
        approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS,
        options_provider=StaticOptions(options),
        filter_builder=ExactAndDateFilters(filters),
        **service_callbacks(feature, title=title),
    )

OUTSIDE_WORK_DEFINITION = _definition(
    "OUTSIDE_WORK", "EC Outside Work Request", "outside_work",
    ("request_title", "work_type", "start_date", "end_date", "duration_days", "remarks",
     "request_attachment", "department", "company"),
    ("name", "request_title", "work_type", "start_date", "end_date", "duration_days",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "work_type", "start_date", "end_date", "duration_days",
     "department", "creation"),
    options=(("work_types", ("Key live", "Campaign", "Business trip", "Other")),),
    filters=("work_type",),
)



