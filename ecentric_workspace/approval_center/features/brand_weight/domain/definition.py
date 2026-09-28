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
