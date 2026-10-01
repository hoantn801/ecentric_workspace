# Copyright (c) 2026, eCentric and contributors
"""Lam lai phan DU LIEU cua p242 (01/10/2026).

p242 da LOI tren production: hai process DAILY_TARGET_PROJECT-V1 va DAILY_TARGET_CONSOLIDATED-V1
CUNG approval_type DAILY_TARGET va CUNG Active (du lieu tu 06/07, truoc khi co luat "moi
approval_type mot process Active"). Vi vay `proc.save()` cua bat ky process nao cung bi
ECApprovalProcess.validate chan ("Another Active process already exists..."), roi rollback
cuon luon ca Role EC Data Team vua tao. Trang page da resync binh thuong.

Ban nay KHONG goi proc.save(): chen thang dong EC Approval Participant (Fulfiller = Role
EC Data Team) vao tung process bang db_insert, giu nguyen trang thai Active cua ca hai.
Hai process cung Active la co chu y (route theo pham vi Project / Consolidated) - KHONG retire.
Moi buoc commit rieng; idempotent; ket qua ghi Error Log. Khong nem loi."""
import frappe

ROLE = "EC Data Team"
PROCESSES = ("DAILY_TARGET_PROJECT-V1", "DAILY_TARGET_CONSOLIDATED-V1")
CHILD = "EC Approval Participant"


def _ensure_role(ket):
    if frappe.db.exists("Role", ROLE):
        ket.append("Role %s da co" % ROLE)
        return
    r = frappe.new_doc("Role")
    r.role_name = ROLE
    r.desk_access = 0
    r.insert(ignore_permissions=True)
    ket.append("Da tao Role %s (chua gan cho ai)" % ROLE)


def _add_fulfiller(code, ket):
    if not frappe.db.exists("EC Approval Process", code):
        ket.append("khong co %s" % code)
        return
    rows = frappe.get_all(CHILD, filters={"parent": code, "parenttype": "EC Approval Process",
                                          "parentfield": "participants"},
                          fields=["participant_purpose", "role", "idx"])
    if any(r.participant_purpose == "Fulfiller" and r.role == ROLE for r in rows):
        ket.append("%s da co Fulfiller" % code)
        return
    child = frappe.get_doc({
        "doctype": CHILD, "parent": code, "parenttype": "EC Approval Process",
        "parentfield": "participants", "idx": max([r.idx or 0 for r in rows] or [0]) + 1,
        "participant_purpose": "Fulfiller", "source_type": "Role", "role": ROLE,
        "sort_order": len(rows)})
    child.db_insert()
    frappe.db.set_value("EC Approval Process", code, "modified", frappe.utils.now(),
                        update_modified=False)
    ket.append("Da them Fulfiller %s vao %s (db_insert, khong qua save)" % (ROLE, code))


def execute():
    ket = []
    for step, arg in [(_ensure_role, None)] + [(_add_fulfiller, c) for c in PROCESSES]:
        try:
            step(ket) if arg is None else step(arg, ket)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("LOI %s\n%s" % (arg or "role", frappe.get_traceback()))
    frappe.log_error(title="p244 daily target fulfiller", message="\n".join(ket))
