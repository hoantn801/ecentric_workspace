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

HIRING_REQUEST_DEFINITION = _definition(
    "HIRING_REQUEST", "EC Hiring Request", "hiring_request",
    ("request_title", "position", "number_of_vacancy", "reason", "employment_type",
     "education", "department", "line_manager", "suggested_salary", "request_attachment", "company"),
    ("name", "request_title", "position", "department", "number_of_vacancy", "employment_type",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "position", "department", "number_of_vacancy", "employment_type", "creation"),
    DepartmentOptions((("reasons", ("New", "Replace")),
                       ("employment_types", ("Full-time", "Freelancer", "Intern")))),
    ("employment_type",),
)



