# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition cho Offer Request (28/09/2026)."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.offer_request.application.service"

OFFER_REQUEST_DEFINITION = ApprovalDefinition(
    code="OFFER_REQUEST", business_doctype="EC Offer Request", feature="offer_request",
    #: Vi tri / phong ban / line manager / loai hinh KHONG nam day: chung chep tu Hiring o
    #: `prepare_draft` - nguoi gui Offer khong chon duoc nguoi duyet cap 1.
    editable_fields=("request_title", "hiring_request", "candidate_name", "onboard_date",
                     "probation_end_date", "mobile_phone", "company_laptop", "compensation",
                     "note", "resume", "offered_salary"),
    my_request_fields=("name", "request_title", "candidate_name", "position", "department",
                       "onboard_date", "hiring_request", "approval_request",
                       "new_staff_preparation", "creation", "modified"),
    approval_list_fields=("name", "request_title", "candidate_name", "position", "department",
                          "onboard_date", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("hiring_request",)),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "offer_block"),
    #: Muc luong la thoa thuan voi ung vien - AI khong duoc dien ho tu CV.
    ai_exclude_fields=("compensation", "offered_salary"),
    **service_callbacks("offer_request", title=True))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
OFFER_REQUEST_DEFINITION = _dc_replace(
    OFFER_REQUEST_DEFINITION,
    quick_summary=(
        ("Ứng viên", "candidate_name"),
        ("Vị trí", "position"),
        ("Ngày onboard", "onboard_date"),
    ),
)


# HR v2 (23/11/2026): nguoi CHI theo doi (neu co) khong thay luong - hop dong Dot 0, chi khai khi
# engine da co truong nay.
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition as _AD  # noqa: E402

OFFER_REQUEST_DEFINITION = _dc_replace(
    OFFER_REQUEST_DEFINITION,
    **{k: v for k, v in {"watcher_hidden_fields": ("compensation", "offered_salary"),
                         # 23/11: TA gui offer khong tu duyet buoc CnB/HR (opt-in, F12).
                         "block_self_approval": True}.items()
       if k in getattr(_AD, "__dataclass_fields__", {})})
