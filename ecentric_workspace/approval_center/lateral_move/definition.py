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

LATERAL_MOVE_DEFINITION = _definition(
    "LATERAL_MOVE", "EC Lateral Move Request", "lateral_move",
    ("request_title", "new_position", "new_department", "new_line_manager", "transfer_reason",
     "start_date", "company"),
    ("name", "request_title", "new_position", "new_department", "start_date",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "new_position", "new_department", "start_date", "department", "creation"),
    options=(("new_departments", ("E-commerce Operation", "Service", "Business Development",
             "Product", "Finance and Accounting", "Operations", "Data & System", "Human Resources")),),
    filters=("new_department",),
)



