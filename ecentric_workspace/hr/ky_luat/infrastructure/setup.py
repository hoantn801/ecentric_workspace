# Copyright (c) 2026, eCentric and contributors
"""Seed module Ky luat - CHI TAO KHI CON THIEU, khong sua / xoa ban ghi HR da chinh tren site.

  * EC Discipline Settings: gia tri mac dinh (SLA noi bo, ghi chu phap ly, role ky = EC CEO) +
    dai dien cong doan = SEED_UNION_REP (Hoan chot 23/11) neu tai khoan ton tai va o con trong.
  * EC Discipline Rule: vai dieu khoan MAU TAM (is_sample = 1) de form dung duoc ngay - HR thay
    bang noi quy da dang ky truoc khi dung that. Ten dieu khoan khong trich nguyen van noi quy nao.
Email chi nam o day (seed), code chay doc tu Settings."""
import frappe

from ecentric_workspace.hr.ky_luat import constants as C

SEED_UNION_REP = "tuan.ly@ecentric.vn"
SAMPLE_RULES = (
    ("MAU-01", "Đi muộn / về sớm nhiều lần không lý do", "Thẻ vàng", 0),
    ("MAU-02", "Không tuân thủ quy trình, hướng dẫn công việc", C.CARD_RED, 0),
    ("MAU-03", "Vắng mặt không xin phép", C.CARD_RED, 0),
    ("MAU-04", "Làm thất thoát, hư hỏng tài sản công ty", C.CARD_BLACK, 1),
    ("MAU-05", "Tiết lộ thông tin, bí mật kinh doanh", C.CARD_BLACK, 1),
    ("MAU-06", "Ứng xử thiếu chuẩn mực với đồng nghiệp / khách hàng", C.CARD_RED, 0),
)
DEFAULTS = {
    "legal_note": C.LEGAL_NOTE, "signer_role": C.DEFAULT_SIGNER_ROLE,
    "notice_reply_days": C.DEFAULT_NOTICE_REPLY_DAYS, "hr_review_days": C.DEFAULT_HR_REVIEW_DAYS,
    "meeting_notice_days": C.DEFAULT_MEETING_NOTICE_DAYS, "ceo_sign_days": C.DEFAULT_CEO_SIGN_DAYS,
    "limitation_warn_days": C.DEFAULT_LIMITATION_WARN_DAYS,
}


def seed_settings():
    doc = frappe.get_single(C.SETTINGS)
    changed = []
    for k, v in DEFAULTS.items():
        if not doc.get(k):
            doc.set(k, v)
            changed.append(k)
    if not doc.get("union_rep_user") and frappe.db.exists("User", SEED_UNION_REP):
        doc.union_rep_user = SEED_UNION_REP
        changed.append("union_rep_user")
    if changed:
        doc.save(ignore_permissions=True)
    return changed


def seed_rules():
    made = []
    for code, title, card, finance in SAMPLE_RULES:
        if frappe.db.exists(C.RULE, code):
            continue
        frappe.get_doc({"doctype": C.RULE, "code": code, "title": title + " (mẫu tạm)",
                        "suggested_card": card, "finance_related": finance, "is_active": 1,
                        "is_sample": 1,
                        "description": "Mẫu tạm - HR thay bằng điều khoản nội quy đã đăng ký."}).insert(
            ignore_permissions=True)
        made.append(code)
    return made
