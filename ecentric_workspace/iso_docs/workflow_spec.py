# Copyright (c) 2026, eCentric and contributors
"""Workflow "Tai lieu ISO" tren Quality Procedure - dac ta THUAN (patch p001 ap len site, test
kiem truc tiep). Trinh tu theo QT Quan ly tai lieu 3.0: Truong BP -> Ban ISO -> TGD -> ban hanh.
Sua nho (X.Y+1) thi Ban ISO ban hanh luon, khong qua TGD. Tai lieu moi luon qua TGD.

Truong BP / nguoi soan khong co role rieng: role Employee + dieu kien tren doc (Frappe Workflow
cho dieu kien doc `frappe.session.user`). Truong BP = Department.manager_email (service dien vao
ec_dept_head). Phong chua co truong BP -> Ban ISO bam thay.
"""
from ecentric_workspace.iso_docs import constants as C

ISO, CEO, EMP = C.ROLE_ISO, C.ROLE_CEO, C.ROLE_EMPLOYEE

IS_DRAFTER = "doc.ec_drafter == frappe.session.user"
IS_HEAD = "doc.ec_dept_head == frappe.session.user"
NO_HEAD = "not doc.ec_dept_head"
NEEDS_CEO = 'doc.ec_change_kind != "Nhỏ" or not doc.ec_current_version'
MINOR = 'doc.ec_change_kind == "Nhỏ" and doc.ec_current_version'

#: (trang thai, style) - doc_status 0 het (Quality Procedure khong submit)
STATES = (
    (C.S_DRAFT, ""), (C.S_HEAD, "Warning"), (C.S_ISO, "Warning"), (C.S_CEO, "Warning"),
    (C.S_PUBLISHED, "Success"), (C.S_WITHDRAW, "Danger"), (C.S_EXPIRED, "Inverse"),
)

#: (trang thai, role duoc sua form) - mot trang thai nhieu dong = nhieu role
EDIT_ROLES = (
    (C.S_DRAFT, ISO), (C.S_DRAFT, EMP),
    (C.S_HEAD, ISO), (C.S_HEAD, EMP),
    (C.S_ISO, ISO),
    (C.S_CEO, ISO), (C.S_CEO, CEO),
    (C.S_PUBLISHED, ISO),
    (C.S_WITHDRAW, ISO), (C.S_WITHDRAW, CEO),
    (C.S_EXPIRED, ISO),
)

A_SEND = "Gửi trưởng bộ phận"
A_AGREE = "Đồng ý"
A_RETURN = "Trả lại"
A_TO_CEO = "Trình Tổng giám đốc"
A_PUBLISH = "Ban hành"
A_APPROVE = "Phê duyệt"
A_NEW = "Soạn phiên bản mới"
A_ASK_WITHDRAW = "Đề nghị thu hồi"
A_WITHDRAW = "Thu hồi"
A_KEEP = "Giữ lại"
A_REDRAFT = "Soạn lại"

#: (tu, hanh dong, den, role, dieu kien)
TRANSITIONS = (
    (C.S_DRAFT, A_SEND, C.S_HEAD, ISO, ""),
    (C.S_DRAFT, A_SEND, C.S_HEAD, EMP, IS_DRAFTER),
    (C.S_HEAD, A_AGREE, C.S_ISO, EMP, IS_HEAD),
    (C.S_HEAD, A_AGREE, C.S_ISO, ISO, NO_HEAD),
    (C.S_HEAD, A_RETURN, C.S_DRAFT, EMP, IS_HEAD),
    (C.S_HEAD, A_RETURN, C.S_DRAFT, ISO, NO_HEAD),
    (C.S_ISO, A_TO_CEO, C.S_CEO, ISO, NEEDS_CEO),
    (C.S_ISO, A_PUBLISH, C.S_PUBLISHED, ISO, MINOR),
    (C.S_ISO, A_RETURN, C.S_DRAFT, ISO, ""),
    (C.S_CEO, A_APPROVE, C.S_PUBLISHED, CEO, ""),
    (C.S_CEO, A_RETURN, C.S_DRAFT, CEO, ""),
    (C.S_PUBLISHED, A_NEW, C.S_DRAFT, ISO, ""),
    (C.S_PUBLISHED, A_NEW, C.S_DRAFT, EMP, IS_HEAD),
    (C.S_PUBLISHED, A_ASK_WITHDRAW, C.S_WITHDRAW, ISO, ""),
    (C.S_WITHDRAW, A_WITHDRAW, C.S_EXPIRED, CEO, ""),
    (C.S_WITHDRAW, A_KEEP, C.S_PUBLISHED, CEO, ""),
    (C.S_EXPIRED, A_REDRAFT, C.S_DRAFT, ISO, ""),
)

ACTIONS = tuple(sorted({a for _f, a, _t, _r, _c in TRANSITIONS}))
