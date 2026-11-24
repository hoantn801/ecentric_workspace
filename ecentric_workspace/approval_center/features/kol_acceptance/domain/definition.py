# Copyright (c) 2026, eCentric and contributors
"""Approval definition cho MOT DOT NGHIEM THU (BBNT) cua hop dong KOL/KOC (PO chot 24/11/2026).

Phieu TU TAO tu the KOL tren form 27 (Account / Ke toan bam "Tao BBNT") - khong ai tao / sua tay:
editable_fields rong, draft_preparer chan tao moi, submit / resubmit chung bi chan (gui qua
contract_review.application.kol_acceptance de kiem thieu thong tin + sinh lai BBNT).
Chuoi duyet KOL_ACCEPTANCE-V1: Ke toan tong hop -> Ke toan truong -> CEO (infrastructure/setup.py).
Duyet o "Cho toi duyet" (the duyet nhanh, quick_summary) hoac popup "Tat ca yeu cau"; trang day du
= form 27 cua hop dong (route cua EC Approval Type).
PO 24/11 cau 3: nguoi trong luong duyet xem duoc ban BBNT du CCCD/STK - attachment_redactor.
"""
from dataclasses import replace as _dc_replace

from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks)
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)

_BASE = "ecentric_workspace.approval_center.features.kol_acceptance.application.service"

KOL_ACCEPTANCE_DEFINITION = ApprovalDefinition(
    code="KOL_ACCEPTANCE", business_doctype="EC KOL Acceptance",
    feature="kol_acceptance",
    editable_fields=(),
    my_request_fields=("name", "request_title", "contract", "contract_no", "round_no", "creator_name",
                       "amount", "status", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "contract_no", "round_no", "creator_name", "amount",
                          "acceptance_date", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("contract", "contract_no")),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "round_block"),
    attachment_redactor=ServiceMethod(_BASE, "redact_attachments"),
    business_redactor=ServiceMethod(_BASE, "redact_business"),
    quick_summary=(("Hợp đồng", "contract_no"), ("Creator", "creator_name"), ("Đợt", "round_no"),
                   ("Số tiền đợt", "amount"), ("Ngày nghiệm thu", "acceptance_date")),
    **service_callbacks("kol_acceptance"))

# Quy trinh A-Z: cac buoc SAU khi duyet xong.
KOL_ACCEPTANCE_DEFINITION = _dc_replace(
    KOL_ACCEPTANCE_DEFINITION,
    journey_after=(
        ("Ký BBNT", "Ký trên cổng ký số, hoặc ký tay rồi tải bản ký lên thẻ KOL của hợp đồng", "info"),
        ("Kế toán kiểm bản ký", "Đạt thì đợt Hoàn tất và được tính vào trần ĐNTT", "info"),
    ),
)
