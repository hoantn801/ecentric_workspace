"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentRows, ExactAndDateFilters, StaticOptions, service_callbacks,
)


def _make(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, feature=feature, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters), **service_callbacks(feature))

ASSET_REQUEST_DEFINITION = _make(
    "ASSET_REQUEST", "EC Asset Request", "asset_request",
    ("request_title", "request_type", "asset_type", "asset_type_other", "purpose_of_request",
     "purpose_other", "quantity", "specifications", "justification", "requested_needed_date",
     "request_attachment", "department", "company"),
    ("name", "request_title", "request_type", "asset_type", "quantity", "requested_needed_date",
     "operation_expected_completion_date", "fulfillment_status", "approval_request", "creation", "modified"),
    ("name", "request_title", "request_type", "asset_type", "quantity", "requested_needed_date",
     "department", "creation"),
    StaticOptions((("request_types", ("Request new asset", "Return old asset")),
       ("asset_types", ("Laptop", "Desktop computer", "Monitor", "Mobile device", "Printer", "RAM", "Other")),
       ("purposes", ("New employee", "Replacement of damaged or obsolete asset",
                     "Additional asset for current use", "Offboarding", "Laptop Allowance", "Other")))),
    ("request_type",))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
ASSET_REQUEST_DEFINITION = _dc_replace(
    ASSET_REQUEST_DEFINITION,
    quick_summary=(
        ("Loại yêu cầu", "request_type"),
        ("Tài sản", "asset_type"),
        ("Số lượng", "quantity"),
        ("Cần ngày", "requested_needed_date"),
    ),
)
