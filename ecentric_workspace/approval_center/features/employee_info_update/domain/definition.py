"""Stateless definition preserving the Employee Info Update response contract.

29/09/2026: danh sach "Field to update" lay tu ho so nhan vien (profile_fields.py) qua
form_options; ket qua ghi vao ho so hien o chi tiet (eiu_block)."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    ServiceMethod,
    service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.employee_info_update.application.service"

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
    options_provider=ServiceMethod(_BASE, "form_options"),
    filter_builder=ExactAndDateFilters(),
    approval_projection="legacy_level_name",
    detail_extender=ServiceMethod(_BASE, "eiu_block"),
    # CCCD, so tai khoan... khong gui sang AI dien ho.
    ai_exclude_fields=("current_value", "new_value"),
    **service_callbacks("employee_info_update", title=True),
)
