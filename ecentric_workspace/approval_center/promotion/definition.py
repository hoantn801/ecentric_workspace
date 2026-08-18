"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentOptions,
    ExactAndDateFilters,
    service_callbacks,
)


def _definition(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters),
        **service_callbacks(feature),
    )

PROMOTION_DEFINITION = _definition(
    "PROMOTION_REQUEST", "EC Promotion Request", "promotion",
    ("request_title", "full_name", "department", "current_position", "proposed_position",
     "justification", "current_salary", "proposed_salary", "incentives",
     "effective_date_of_promotion", "company"),
    ("name", "request_title", "full_name", "proposed_position", "effective_date_of_promotion",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "full_name", "proposed_position", "effective_date_of_promotion",
     "department", "creation"),
    DepartmentOptions(),
    ("proposed_position",),
)



