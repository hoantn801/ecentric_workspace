"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentOptions,
    ExactAndDateFilters,
    ServiceMethod,
    service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.hiring_request.application.service"


def _definition(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters),
        feature=feature,
        # 28/09: man hinh chi tiet can biet cac Offer da tao va nguoi xem co duoc "Tao Offer".
        detail_extender=ServiceMethod(_BASE, "hiring_block"),
        **service_callbacks(feature),
    )

HIRING_REQUEST_DEFINITION = _definition(
    "HIRING_REQUEST", "EC Hiring Request", "hiring_request",
    ("request_title", "position", "number_of_vacancy", "reason", "employment_type",
     "education", "department", "line_manager", "suggested_salary", "request_attachment", "company"),
    ("name", "request_title", "position", "department", "number_of_vacancy", "employment_type",
     "approval_request", "fulfillment_status", "fulfillment_owner", "creation", "modified"),
    ("name", "request_title", "position", "department", "number_of_vacancy", "employment_type",
     "fulfillment_status", "creation"),
    DepartmentOptions((("reasons", ("New", "Replace")),
                       ("employment_types", ("Full-time", "Freelancer", "Intern")))),
    ("employment_type",),
)


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
HIRING_REQUEST_DEFINITION = _dc_replace(
    HIRING_REQUEST_DEFINITION,
    quick_summary=(
        ("Vị trí", "position"),
        ("Số lượng", "number_of_vacancy"),
        ("Lý do", "reason"),
        ("Loại hình", "employment_type"),
    ),
)
