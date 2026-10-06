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

DOCUMENT_REQUEST_DEFINITION = _make(
    "DOCUMENT_REQUEST", "EC Document Request", "document_request",
    ("request_title", "request_type", "document_name", "owner_department", "detail",
     "expected_response_date", "request_attachment", "department", "company"),
    ("name", "request_title", "request_type", "document_name", "owner_department",
     "expected_response_date", "fulfillment_status", "approval_request", "creation", "modified"),
    ("name", "request_title", "request_type", "document_name", "owner_department",
     "expected_response_date", "department", "creation"), DepartmentRows(), ("request_type",))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
DOCUMENT_REQUEST_DEFINITION = _dc_replace(
    DOCUMENT_REQUEST_DEFINITION,
    quick_summary=(
        ("Loại", "request_type"),
        ("Tài liệu", "document_name"),
        ("Cần ngày", "expected_response_date"),
    ),
)
