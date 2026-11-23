# Copyright (c) 2026, eCentric and contributors
"""Approval definition cho buoc CEO KY QUYET DINH KY LUAT (Dot 3 HR, 23/11/2026).

Phieu TU TAO tu ho so EC Discipline Case (hr/ky_luat) khi HR "Trinh CEO" - khong ai tao / sua
tay (editable_fields rong, draft_preparer chan). 1 cap: role ky (mac dinh EC CEO, EC Discipline
Settings.signer_role). Ky so: neu co EC Digital Signature Profile BAT cho cap (EC Discipline
Decision Request, DISCIPLINE_DECISION) thi cap nay bat ky nhu moi form khac (cau hinh, khong code).

Rieng tu (`private`) + chan tu duyet (`subject_fields`) theo hop dong Dot 0 (HR_DOT0_INTERFACE.md):
chi khai khi engine da co truong do - nhanh nay doc lap voi nhanh Dot 0, gop xong la tu bat.
Khong vao duyet hang loat (`quick_comment_required`): quyet dinh ky luat phai mo xem tung ho so.
"""
from dataclasses import replace as _dc_replace

from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks)
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)

_BASE = "ecentric_workspace.approval_center.features.discipline_decision.application.service"

DISCIPLINE_DECISION_DEFINITION = ApprovalDefinition(
    code="DISCIPLINE_DECISION", business_doctype="EC Discipline Decision Request",
    feature="discipline_decision",
    editable_fields=(),
    my_request_fields=("name", "request_title", "employee_name", "penalty", "effective_date",
                       "discipline_case", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "employee_name", "penalty", "meeting_date",
                          "limitation_effective_end", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("discipline_case", "penalty")),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "decision_block"),
    quick_comment_required=True,
    quick_summary=(("Nhân viên", "employee_name"), ("Hình thức", "penalty"),
                   ("Ngày họp", "meeting_date"), ("Hết thời hiệu", "limitation_effective_end")),
    **service_callbacks("discipline_decision"))

_DOT0 = (("private", True), ("subject_fields", ("employee",)), ("block_self_approval", True))
_HAS = getattr(ApprovalDefinition, "__dataclass_fields__", {})
_EXTRA = {k: v for k, v in _DOT0 if k in _HAS}
if _EXTRA:
    DISCIPLINE_DECISION_DEFINITION = _dc_replace(DISCIPLINE_DECISION_DEFINITION, **_EXTRA)
