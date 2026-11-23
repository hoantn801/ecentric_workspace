# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition cho Danh gia nhan su (EMPLOYEE_REVIEW, 23/11/2026)."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.employee_review.application.service"

EMPLOYEE_REVIEW_DEFINITION = ApprovalDefinition(
    code="EMPLOYEE_REVIEW", business_doctype="EC Employee Review", feature="employee_review",
    #: Phieu TU TAO tu bang hop dong tren ho so (hoac C&B tao tu trang hang cho). Nguoi gui (C&B)
    #: chi sua duoc ghi chu + mau tieu chi; doi tuong / dong hop dong la ban chup.
    editable_fields=("request_title", "ghi_chu_cnb", "mau_tieu_chi"),
    my_request_fields=("name", "request_title", "review_type", "ten_nhan_vien", "hd_den_ngay",
                       "auto_submit_on", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "review_type", "ten_nhan_vien", "hd_den_ngay",
                          "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions((("review_types", ("Thử việc", "Thực tập", "Hợp đồng")),)),
    filter_builder=ExactAndDateFilters(("review_type",)),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "review_block"),
    #: Nhan xet + ket qua cua LM an voi nhan vien toi khi CEO duyet (Hoan chot 22/11).
    business_redactor=ServiceMethod(_BASE, "redact"),
    #: Duyet nhanh: moi cap phai NHAP noi dung (tu danh gia / nhan xet) - khong duyet hang loat.
    quick_comment_required=True,
    clone_exclude_fields=("ghi_chu_cnb",),
    ai_exclude_fields=("ghi_chu_cnb", "mau_tieu_chi"),
    all_tab_filters=("review_type",),
    #: RIENG TU (tich hop Dot 0, 23/11): nhan xet hieu suat + ket qua thu viec / hop dong khong mo cho
    #: truong phong / Approval Admin / tab "Tat ca" / thong ke. Chi C&B gui, NV + LM + CEO (cap duyet)
    #: va nguoi theo doi (dong Notify = role EC CnB trong process) xem duoc. KHONG khai subject_fields:
    #: chinh NV la nguoi duyet cap 1 (tu danh gia) - khai la engine loai NV khoi cap do.
    private=True,
    block_self_approval=True,
    **service_callbacks("employee_review", title=True))


# "Cho toi duyet" tren dien thoai: chi truong ai trong luong cung xem duoc - KHONG dua ket qua /
# nhan xet LM (an voi nhan vien toi khi CEO duyet).
EMPLOYEE_REVIEW_DEFINITION = _dc_replace(
    EMPLOYEE_REVIEW_DEFINITION,
    quick_summary=(
        ("Nhân viên", "ten_nhan_vien"),
        ("Loại", "review_type"),
        ("Hợp đồng đến", "hd_den_ngay"),
    ),
)
