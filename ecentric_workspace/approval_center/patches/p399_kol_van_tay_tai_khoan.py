# Copyright (c) 2026, eCentric and contributors
"""17/11/2026 (PO, quyet dinh D): chot van tay tai khoan nhan tien (kol_access.payee_fp - HMAC, khong luu
so) cho hop dong KOL da gui TRUOC ban nay. Khong co moc thi `payee_changed` luon "khong doi" - creator
doi STK sau deploy se khong ai thay (QC 17/11).

Moc = tai khoan creator HIEN TAI luc migrate (khong biet duoc tai khoan luc ky cua phieu cu). Chi phieu da
gui, chua co moc, khong bi Tu choi / Huy. Loi tung phieu -> Error Log, KHONG nem."""
import frappe

_DT = "EC Contract Review Request"
_KOL = "KOL/KOC / Creator (EC)"


def execute():
    if not frappe.db.exists("DocType", _DT) or not frappe.db.has_column(_DT, "kol_payee_fp"):
        return
    access = frappe.get_module("ecentric_workspace.approval_center.features.contract_review.application.kol_access")
    service = frappe.get_module("ecentric_workspace.approval_center.features.contract_review.application.kol_service")
    rows = frappe.get_all(_DT, filters={"contract_type": _KOL, "approval_request": ["is", "set"]},
                          fields=["name", "creator", "approval_request", "kol_payee_fp"], limit_page_length=0)
    dat = 0
    for r in rows:
        if r.kol_payee_fp or not r.creator:
            continue
        try:
            if frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status") in ("Rejected",
                                                                                                    "Cancelled"):
                continue
            fp = access.payee_fp(service.creator_row(r.creator))
            if fp:
                frappe.db.set_value(_DT, r.name, "kol_payee_fp", fp, update_modified=False)
                dat += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p399 van tay tai khoan %s" % r.name)
    frappe.logger("approval_center").info("p399: chot van tay tai khoan %s / %s hop dong KOL" % (dat, len(rows)))
