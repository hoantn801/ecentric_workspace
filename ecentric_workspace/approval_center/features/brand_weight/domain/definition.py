"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    StaticOptions,
    service_callbacks,
)

# Ty trong khong sua qua form chung (editable_fields rong): chi trang Phan bo cong viec
# ghi duoc, vi o do moi co validate tong 100% + luat bo cap + so de xuat/lead tach rieng.
BRAND_WEIGHT_DEFINITION = ApprovalDefinition(
    code="BRAND_WEIGHT",
    business_doctype="EC Brand Weight Request",
    editable_fields=(),
    my_request_fields=("name", "request_title", "period", "total_weight", "approval_request",
                       "creation", "modified"),
    approval_list_fields=("name", "request_title", "period", "total_weight", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("period",)),
    **service_callbacks("brand_weight"),
)


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
BRAND_WEIGHT_DEFINITION = _dc_replace(
    BRAND_WEIGHT_DEFINITION,
    quick_summary=(
        ("Kỳ", "period"),
        ("Tổng tỷ trọng", "total_weight"),
    ),
)
