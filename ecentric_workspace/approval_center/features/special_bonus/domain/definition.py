"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
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

SPECIAL_BONUS_DEFINITION = _definition(
    "SPECIAL_BONUS", "EC Special Bonus Request", "special_bonus",
    ("request_title", "department", "project_name", "reasons", "total_bonus",
     "request_attachment", "company"),
    ("name", "request_title", "department", "project_name", "total_bonus",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "project_name", "total_bonus", "department", "creation"),
    DepartmentOptions(),
    ("project_name",),
)


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
SPECIAL_BONUS_DEFINITION = _dc_replace(
    SPECIAL_BONUS_DEFINITION,
    quick_summary=(
        ("Dự án", "project_name"),
    ),
)
