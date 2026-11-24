# Copyright (c) 2026, eCentric and contributors
"""p523: doi cac loai phieu NHAN SU tu nhom "Hanh chinh" (ADMINISTRATION) / "Khac" (OTHERS) sang
nhom "Nhan su" (HR) tren Approval Center (Hoan chot 24/11/2026: "ok nhe").

Chi doi truong `category` cua EC Approval Type da co, theo DANH SACH GO TAY - khong xoa / tao lai,
khong dong card_status / route / quy trinh. Loai da o nhom khac (vd ai do da tu doi) thi chi doi khi
dang o dung nhom cu ghi ben duoi, de khong ghi de lua chon tay. Idempotent.

Giu o Hanh chinh: DOCUMENT_REQUEST (xin giay to), ASSET_DAMAGE_LOSS (bao hong tai san).
Luu y: setup cua tung feature chi gan category LUC TAO (exists -> return), nen site nay khong bi
doi nguoc khi migrate; site moi cai tu dau van ra ADMINISTRATION cho den khi sua setup."""
import frappe

TYP = "EC Approval Type"
CAT = "EC Approval Category"
HR = "HR"

#: code -> nhom cu duoc phep doi
DOI = {
    "HIRING_REQUEST": "ADMINISTRATION",
    "OFFER_REQUEST": "ADMINISTRATION",
    "NEW_STAFF_PREPARATION": "ADMINISTRATION",
    "EMPLOYEE_INFO_UPDATE": "ADMINISTRATION",
    "PROMOTION_REQUEST": "ADMINISTRATION",
    "LATERAL_MOVE": "ADMINISTRATION",
    "EMPLOYEE_REVIEW": "ADMINISTRATION",
    "DISCIPLINE_DECISION": "ADMINISTRATION",
    "RESIGNATION": "ADMINISTRATION",
    "CLEARANCE_REQUEST": "ADMINISTRATION",
    "EMPLOYEE_REFERRAL": "OTHERS",
}


def execute():
    if not frappe.db.exists("DocType", TYP) or not frappe.db.exists(CAT, HR):
        return
    doi, bo_qua = [], []
    for code, cu in DOI.items():
        if not frappe.db.exists(TYP, code):
            continue
        hien = frappe.db.get_value(TYP, code, "category")
        if hien == HR:
            continue
        if hien != cu:
            bo_qua.append("%s(%s)" % (code, hien))
            continue
        frappe.db.set_value(TYP, code, "category", HR)
        doi.append(code)
    frappe.db.commit()
    print("[p523] sang nhom Nhan su: %s; bo qua (nhom da doi tay): %s" % (doi or "-", bo_qua or "-"))
