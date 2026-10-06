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


def _definition(code, doctype, feature, editable, mine, approvals, options=(), filters=(), title=False):
    return ApprovalDefinition(
        code=code,
        business_doctype=doctype,
        editable_fields=editable,
        my_request_fields=mine,
        approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS,
        options_provider=StaticOptions(options),
        filter_builder=ExactAndDateFilters(filters),
        **service_callbacks(feature, title=title),
    )

SERVICE_REFERRAL_DEFINITION = _definition(
    "SERVICE_REFERRAL", "EC Service Referral Request", "service_referral",
    ("client", "brand", "contact_name", "contact_phone_number", "contact_email",
     "estimated_contract_value", "justification", "request_attachment", "department", "company"),
    ("name", "request_title", "client", "brand", "estimated_contract_value",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "client", "brand", "estimated_contract_value", "department", "creation"),
    filters=("brand",),
    title=True,
)


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
SERVICE_REFERRAL_DEFINITION = _dc_replace(
    SERVICE_REFERRAL_DEFINITION,
    quick_summary=(
        ("Khách hàng", "client"),
        ("Brand", "brand"),
        ("Giá trị ước tính", "estimated_contract_value"),
    ),
)
