# Copyright (c) 2026, eCentric and contributors
"""Dua don hieu/hi/thai san dang cho ve buoc LEAD theo luong moi (24/09, Hoan chot).

LUONG CU: don sinh thang o buoc 'hr' -> Nhan su ky -> CEO ky buoc cuoi. Quan ly
truc tiep hoan toan khong nam trong duong duyet.
LUONG MOI: 'lead' -> 'hr' -> xong, CC cho CEO. Hai chu ky nhung la hai nguoi sat
viec hon, va CEO khong con la nut that.

Patch nay xu ly nhung don LO NOP TRUOC khi doi: chung dang dung o buoc 'hr' cua
luong cu. Neu de nguyen, Nhan su ky mot chu la don xong luon - tuc la quan ly van
khong duoc hoi. Hoan chon dua chung ve dung luong moi.

Tai sao doi nguoi duyet va ToDo chu khong chi doi mot truong: `leave_approver` la
cai quyet dinh ToDo hien trong 'Viec can lam' cua ai. Doi stage ma quen hai thu kia
thi don im lang nam o danh sach cua nguoi khong con trach nhiem - dung kieu hong
vua phai sua.

Chi dung toi don CHUA xu ly (docstatus=0, status='Open'). Don da duyet/tu choi
khong dong toi. KHONG BAO GIO nem loi: patch chay trong migrate. Idempotent -
chay lai lan hai thi khong con don nao khop dieu kien.
"""
import frappe

TWO_STEP = ("Marriage Leave", "Bereavement Leave", "Maternity Leave", "Paternity Leave")


def execute():
    try:
        rows = frappe.get_all(
            "Leave Application",
            filters={"docstatus": 0, "status": "Open",
                     "ec_approval_stage": "hr", "leave_type": ["in", TWO_STEP]},
            fields=["name", "employee", "employee_name", "leave_type", "from_date"],
        )
        if not rows:
            return
        done = []
        for r in rows:
            lead = _lead_cua(r["employee"])
            if not lead:
                # Khong tim duoc cap tren nao -> DE NGUYEN o buoc 'hr'. Day ve 'lead'
                # ma khong co ai o buoc do thi don ket cung, te hon hien trang.
                continue
            frappe.db.set_value("Leave Application", r["name"],
                                {"ec_approval_stage": "lead", "leave_approver": lead},
                                update_modified=False)
            _chuyen_todo(r, lead)
            done.append(r["name"] + " -> " + lead)
        if done:
            frappe.log_error("dua ve buoc lead: " + ", ".join(done),
                             "p001 leave two step back to lead")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p001 leave two step back to lead")


def _lead_cua(employee):
    """Cap tren gan nhat trong cay ma con dung duoc tai khoan - giong het cach
    ec_hr_leave_apply chon lead, de hai duong khong bao gio tra ve hai nguoi."""
    me = frappe.db.get_value("Employee", employee, ["lft", "rgt"], as_dict=True)
    if not me or me.lft is None:
        return None
    hit = frappe.db.sql(
        "select user_id from `tabEmployee` where lft < %s and rgt > %s"
        " and status='Active' and ifnull(user_id,'') <> ''"
        " order by lft desc limit 1", (me.lft, me.rgt))
    return hit[0][0] if hit else None


def _chuyen_todo(r, lead):
    """Dong nhac viec cu va mo lai cho lead. Khong dong thi don hien o ca hai cho."""
    olds = frappe.get_all("ToDo", filters={"reference_type": "Leave Application",
                                           "reference_name": r["name"],
                                           "status": "Open"}, pluck="name")
    for nm in olds:
        frappe.db.set_value("ToDo", nm, "status", "Closed", update_modified=False)
    frappe.get_doc({
        "doctype": "ToDo", "allocated_to": lead, "status": "Open", "priority": "Medium",
        "reference_type": "Leave Application", "reference_name": r["name"],
        "date": r["from_date"],
        "description": "Duyet don nghi phep: %s - %s" % (r["employee_name"], r["leave_type"]),
    }).insert(ignore_permissions=True)
