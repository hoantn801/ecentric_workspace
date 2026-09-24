# Copyright (c) 2026, eCentric and contributors
"""Huy EC-CTR-2026-00024 (EC-APR-2026-00376) - da Approved nhung cap Finance bi duyet nham vai tro.

CHUYEN GI DA XAY RA (25/09, Hoan). Anh Lam tung duoc gan nham role `EC Finance`. Cap 2
"Finance Team Review" cua CONTRACT_REVIEW-V1 resolve theo role do va chay kieu Any One, nen
anh Lam bam duyet la ca cap dong lai - nhom Finance khong ai xem hop dong. Cap 4 CEO sau do
TU BO QUA (luat "da duyet cap truoc thi khong duyet lai") vi cung la anh Lam. Ket qua: phieu
Approved ma thuc chat chi hai nguoi doc. Hoan chon HUY phieu, team tao phieu moi.

VI SAO PHAI LA PATCH. `cancel()` CO Y chan phieu terminal (`_guard_open`): phieu co buoc thuc
hien se mo coi viec cua nguoi dang xu ly. Contract Review KHONG co buoc thuc hien va KHONG ky
so - patch van KIEM LAI ca hai va dung han neu sai, khong tin vao nhan xet nay.

LAM GI - dung cac buoc cua `transitions.cancel()`, chi bo `_guard_open`:
  * khoa dong, doc lai trang thai duoi khoa;
  * approval_status -> Cancelled, completed_at = bay gio;
  * log_action "Cancelled" (nguoi thuc hien: hoan.tran, kem ly do) - vet kiem toan;
  * dong ToDo, bao nguoi de nghi, `_sla().on_request_cancelled` (chi dong dau viec con MO -
    nghia vu da Met cua nguoi da duyet giu nguyen).
KHONG xoa, KHONG sua dong nguoi duyet nao: ai da bam gi luc nao van con nguyen.

AN TOAN:
  * Chi chay khi phieu con dung la Approved -> chay lai sau khi xong thi bo qua (idempotent).
  * Dung han neu da co phieu phu luc tro `previous_request` vao 00024 - huy phieu goc luc do
    se de mot phu luc tro vao ban khong con hieu luc; viec do can nguoi quyet, khong phai patch.
  * KHONG BAO GIO nem loi: patch chay trong migrate (p116). Loi -> rollback + Error Log.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as tr

APR = "EC-APR-2026-00376"
CTR = "EC-CTR-2026-00024"
BUSINESS_DT = "EC Contract Review Request"
APPROVAL_TYPE = "CONTRACT_REVIEW"
NGUOI_HUY = "hoan.tran@ecentric.vn"
LY_DO = ("Huy theo yeu cau Hoan (25/09): cap Finance Team Review bi dong boi lam.nguyen qua role "
         "EC Finance gan nham - nhom Finance chua xem hop dong, CEO bi tu bo qua. "
         "Vui long tao phieu moi.")


def _huy():
    if not frappe.db.get_value("EC Approval Request", APR, "name", for_update=True):
        return "bo qua: khong thay %s" % APR
    req = frappe.get_doc("EC Approval Request", APR)
    if req.reference_doctype != BUSINESS_DT or req.reference_name != CTR:
        return "DUNG: %s khong tro vao %s" % (APR, CTR)
    if req.approval_type != APPROVAL_TYPE:
        return "DUNG: sai loai %s" % req.approval_type
    if req.approval_status != "Approved":
        return "bo qua: trang thai %s (da huy roi?)" % req.approval_status
    if req.reference_doctype in getattr(tr, "_FULFILLMENT_HANDLERS", {}):
        return "DUNG: loai phieu co buoc thuc hien - khong huy bang patch nay"
    if tr._luong_co_ky_so(req, "p207_cancel"):
        return "DUNG: luong co ky so - khong huy bang patch nay"
    con = frappe.get_all(BUSINESS_DT, filters={"previous_request": CTR}, pluck="name")
    if con:
        return "DUNG: da co phieu phu luc tro vao %s: %s" % (CTR, ", ".join(con))

    frappe.db.set_value("EC Approval Request", APR,
                        {"approval_status": "Cancelled", "completed_at": now_datetime()})
    tr.log_action(APR, "Cancelled", NGUOI_HUY, 0, comment=LY_DO,
                  previous_status="Approved", new_status="Cancelled")
    tr.close_todos(req.reference_doctype, req.reference_name)
    tr.notify([req.requested_by], "Phieu da bi huy: %s" % CTR, req.reference_doctype, req.reference_name)
    tr._sla().on_request_cancelled(request_doctype=req.reference_doctype,
                                   request_name=req.reference_name)
    return "DA HUY"


def execute():
    try:
        kq = _huy()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p207 huy %s FAILED" % CTR)
        kq = "LOI - xem Error Log"
    frappe.log_error("%s: %s" % (CTR, kq), "p207 huy %s" % CTR)
