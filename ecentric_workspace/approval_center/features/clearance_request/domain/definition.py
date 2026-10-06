# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition cho Clearance Request (29/09/2026)."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.clearance_request.application.service"

CLEARANCE_REQUEST_DEFINITION = ApprovalDefinition(
    code="CLEARANCE_REQUEST", business_doctype="EC Clearance Request",
    feature="clearance_request",
    #: Phieu TU TAO tu Don nghi viec da duyet - ban chup, khong ai sua.
    editable_fields=(),
    my_request_fields=("name", "request_title", "employee_name", "department", "last_working_day",
                       "resignation_request", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "employee_name", "department",
                          "last_working_day", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("resignation_request",)),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "clearance_block"),
    **service_callbacks("clearance_request"))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
CLEARANCE_REQUEST_DEFINITION = _dc_replace(
    CLEARANCE_REQUEST_DEFINITION,
    quick_summary=(
        ("Nhân sự", "employee_name"),
        ("Ngày làm cuối", "last_working_day"),
        ("Quản lý", "line_manager"),
    ),
)
