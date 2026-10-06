"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    ServiceMethod,
    service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.promotion.application.service"


def _definition(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters),
        # 29/09: duyet xong tu cap nhat ho so + luong; ket qua hien o chi tiet.
        detail_extender=ServiceMethod(_BASE, "promotion_block"),
        # Review Phan quyen P1: nguoi xem khong xem duoc luong nhan su do thi khong thay so.
        business_redactor=ServiceMethod(_BASE, "redact_business"),
        ai_exclude_fields=("current_salary", "proposed_salary", "incentives"),
        **service_callbacks(feature),
    )

PROMOTION_DEFINITION = _definition(
    "PROMOTION_REQUEST", "EC Promotion Request", "promotion",
    ("request_title", "promoted_employee", "full_name", "department", "current_position", "proposed_position",
     "justification", "current_salary", "proposed_salary", "incentives",
     "effective_date_of_promotion", "company"),
    ("name", "request_title", "full_name", "proposed_position", "effective_date_of_promotion",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "full_name", "proposed_position", "effective_date_of_promotion",
     "department", "creation"),
    ServiceMethod(_BASE, "form_options"),
    ("proposed_position",),
)


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
PROMOTION_DEFINITION = _dc_replace(
    PROMOTION_DEFINITION,
    quick_summary=(
        ("Nhân sự", "full_name"),
        ("Vị trí hiện tại", "current_position"),
        ("Vị trí đề xuất", "proposed_position"),
        ("Hiệu lực", "effective_date_of_promotion"),
    ),
    quick_comment_required=True,
)
