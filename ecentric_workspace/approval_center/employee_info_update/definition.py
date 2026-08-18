"""Stateless definition preserving the Employee Info Update response contract."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    StaticOptions,
    service_callbacks,
)


EMPLOYEE_INFO_UPDATE_DEFINITION = ApprovalDefinition(
    code="EMPLOYEE_INFO_UPDATE",
    business_doctype="EC Employee Information Update Request",
    editable_fields=("employee_email", "field_to_update", "field_to_update_other",
                     "current_value", "new_value", "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "employee_email", "field_to_update",
                       "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "employee_email", "field_to_update",
                          "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions((("field_to_update_options", (
        "Personal email", "Bank account", "Hospital code", "Mobile phone", "Birthplace",
        "Citizen ID number", "Citizen ID issue date", "Citizen ID issue place",
        "Permanent address", "Temporary address", "Position (C&B use only)", "Other")),)),
    filter_builder=ExactAndDateFilters(),
    approval_projection="legacy_level_name",
    **service_callbacks("employee_info_update", title=True),
)


