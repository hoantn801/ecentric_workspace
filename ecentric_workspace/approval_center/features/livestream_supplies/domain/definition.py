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

LIVESTREAM_SUPPLIES_DEFINITION = _definition(
    "LIVESTREAM_SUPPLIES", "EC Livestream Supplies Request", "livestream_supplies",
    ("supplies", "request_type", "quantity", "justification", "start_date", "end_date",
     "request_attachment", "department", "company"),
    ("name", "request_title", "supplies", "request_type", "quantity", "start_date", "end_date",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "supplies", "request_type", "quantity", "start_date", "end_date",
     "department", "creation"),
    options=(("request_type_options", ("Request supplies", "Return supplies")),),
    title=True,
)



