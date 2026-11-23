# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition - Phe duyet dot xuat gui CEO (23/11/2026)."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, StaticOptions, service_callbacks,
)

#: Gia tri `urgency` (truong theo quy uoc engine: transitions.URGENCY_FIELD / URGENT_VALUES).
URGENCY_LEVELS = ("Bình thường", "Gấp")

ADHOC_APPROVAL_DEFINITION = ApprovalDefinition(
    code="ADHOC_APPROVAL", business_doctype="EC Adhoc Approval Request",
    feature="adhoc_approval",
    #: KHONG co department/company: service tu lay tu ho so Employee luc gui (snapshot khong mo
    #: cho nguoi gui sua - xem test_e2e3_feature_parity department_snapshot).
    editable_fields=("request_title", "content", "urgency", "urgency_reason", "desired_by",
                     "request_attachment"),
    my_request_fields=("name", "request_title", "urgency", "desired_by", "approval_request",
                       "creation", "modified"),
    approval_list_fields=("name", "request_title", "urgency", "desired_by", "department",
                          "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions((("urgency_levels", URGENCY_LEVELS),)),
    filter_builder=ExactAndDateFilters(("urgency",)),
    #: PHIEU RIENG TU: chi nguoi gui, CEO, nguoi theo doi, System Manager (co nhat ky).
    private=True,
    #: Nguoi gui khong tu duyet (vd CEO tu gui) - opt-in, xem contracts.block_self_approval.
    block_self_approval=True,
    #: "Cho toi duyet" tren dien thoai - CEO doc noi dung truoc khi bam.
    quick_summary=(
        ("Mức độ", "urgency"),
        ("Mong muốn trước", "desired_by"),
        ("Lý do gấp", "urgency_reason"),
    ),
    all_tab_columns=(("Mức độ", "urgency", "select"), ("Mong muốn trước", "desired_by", "date")),
    all_tab_filters=("urgency",),
    **service_callbacks("adhoc_approval"))
