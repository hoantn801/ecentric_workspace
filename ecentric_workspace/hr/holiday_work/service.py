# Copyright (c) 2026, eCentric and contributors
"""Danh sach di lam ngay nghi (EC Holiday Work) - xu ly sau khi luu va job hang dem.

Mot dot = mot ngay + danh sach nguoi + cach tinh:
  - counts_as_workday : ngay do la ngay LAM cua nguoi trong danh sach (xem lookup.py).
                        Ai da cham cong dung gio ma chua co Attendance (vi luc cham ngay
                        do con la ngay le) -> ghi bu Attendance Present.
  - leave_bonus_days  : cong phep nam (Annual Leave) mot lan / nguoi, cung kieu but toan
                        cong phep ngay x2 (Server Script ec_hr_double_day).
  - require_checkin   : chi thuong khi co cham cong ngay do. Tat cho ngay cu khong co du
                        lieu cham cong (vd 10/10/2026, truoc khi co may khuon mat).
  - allow_comp_off    : Server Script ec_hr_leave_apply doc truc tiep, file nay khong dung.
  - cash_bonus        : chi ghi nhan cho CnB.
Chay lai bao nhieu lan cung vay: phep da cong co but toan ghi o dong, khong cong lan hai.
"""
import re

import frappe
from frappe.utils import add_days, getdate, nowdate

from ecentric_workspace.hr.holiday_work.lookup import DT

LEAVE_TYPE = "Annual Leave"
CODE_RE = re.compile(r"NV\d{3,}", re.I)


# --------------------------------------------------------------------------- #
# validate: dan ma NV -> them dong; bo trung
# --------------------------------------------------------------------------- #
def parse_codes(text):
    return [c.upper() for c in CODE_RE.findall(text or "")]


def validate(doc):
    have = set()
    rows = []
    for r in doc.get("members") or []:
        if r.employee and r.employee not in have:
            have.add(r.employee)
            rows.append(r)
    if len(rows) != len(doc.get("members") or []):
        doc.set("members", rows)
    codes = parse_codes(doc.get("paste_codes"))
    if codes:
        missing = []
        for code in codes:
            emp = frappe.db.get_value("Employee", {"employee_number": code}, "name")
            if not emp:
                missing.append(code)
                continue
            if emp in have:
                continue
            have.add(emp)
            doc.append("members", {"employee": emp})
        doc.paste_codes = ""
        if missing:
            frappe.msgprint("Không tìm thấy mã nhân viên: %s. Kiểm tra lại MNV trên hồ sơ "
                            "hoặc thêm tay vào bảng." % ", ".join(missing),
                            title="Một số mã chưa thêm được", indicator="orange")
    if doc.get("leave_bonus_days") and float(doc.leave_bonus_days) < 0:
        frappe.throw("Thưởng ngày phép không được âm.")


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #
def _first_checkins(day, employees):
    if not employees:
        return {}
    rows = frappe.db.sql(
        "select employee, min(time) from `tabEmployee Checkin`"
        " where employee in %s and time >= %s and time < %s group by employee",
        (tuple(employees), "%s 00:00:00" % day, "%s 00:00:00" % add_days(day, 1)))
    return {r[0]: r[1] for r in rows}


def _hms(v):
    s = str(v or "")
    return ("0" + s) if len(s) == 7 else s


def _cutoff(shift):
    v = frappe.db.get_value("Shift Type", shift, "ec_checkin_cutoff") if shift else None
    return _hms(v) or "10:00:00"


def _on_leave(employee, day):
    return bool(frappe.db.sql(
        "select 1 from `tabLeave Application` where employee=%s and status='Approved'"
        " and docstatus=1 and %s between from_date and to_date limit 1", (employee, day)))


def _mark_present(emp, day, first):
    """Ghi Attendance Present neu cham cong dung gio va chua co ban ghi. -> True neu ghi."""
    shift = emp.get("default_shift") or "EC Standard 9-18"
    if str(first)[11:19] > _cutoff(shift):
        return False
    if _on_leave(emp["name"], day):
        return False
    if frappe.db.exists("Attendance", {"employee": emp["name"], "attendance_date": day,
                                       "docstatus": ["<", 2]}):
        return False
    att = frappe.get_doc({"doctype": "Attendance", "employee": emp["name"],
                          "attendance_date": day, "status": "Present", "shift": shift,
                          "company": emp.get("company")})
    att.flags.ignore_permissions = True
    att.insert(ignore_permissions=True)
    att.submit()
    return True


def _credit_leave(emp, day, days):
    """Cong `days` ngay phep nam. -> (ten but toan | None, ghi chu)."""
    existing = frappe.db.get_value("Leave Ledger Entry", {
        "employee": emp["name"], "leave_type": LEAVE_TYPE, "from_date": day,
        "leaves": days, "docstatus": 1}, "name")
    if existing:
        return existing, "đã có bút toán phép ngày này"
    alloc = frappe.db.get_value("Leave Allocation", {
        "employee": emp["name"], "leave_type": LEAVE_TYPE, "docstatus": 1,
        "from_date": ["<=", day], "to_date": [">=", day]}, ["name", "to_date"], as_dict=True)
    if not alloc:
        return None, "chưa có quỹ phép năm"
    led = frappe.get_doc({
        "doctype": "Leave Ledger Entry", "employee": emp["name"],
        "employee_name": emp.get("employee_name"), "leave_type": LEAVE_TYPE,
        "transaction_type": "Leave Allocation", "transaction_name": alloc.name,
        "leaves": days, "from_date": day, "to_date": alloc.to_date or ("%s-12-31" % str(day)[:4])})
    led.flags.ignore_permissions = True
    led.insert(ignore_permissions=True)
    led.submit()
    return led.name, ""


def _sla(employee, day):
    try:
        from ecentric_workspace.sla.infrastructure import attendance_source
        attendance_source.sync_one(employee, day)
    except Exception:
        frappe.log_error(title="holiday_work._sla", message=frappe.get_traceback())


def apply(name):
    """Xu ly mot dot. Ngay chua toi -> khong lam gi (job dem se lam). -> report dict."""
    doc = frappe.get_doc(DT, name)
    day = getdate(doc.work_date)
    rep = {"name": name, "present": [], "credited": []}
    if day > getdate(nowdate()):
        return rep
    emps = {}
    for r in doc.members:
        if r.employee and r.employee not in emps:
            emps[r.employee] = frappe.db.get_value(
                "Employee", r.employee,
                ["name", "employee_name", "default_shift", "company"], as_dict=True)
    firsts = _first_checkins(str(day), [e for e in emps if emps[e]])
    days = float(doc.leave_bonus_days or 0)
    for r in doc.members:
        emp = emps.get(r.employee)
        if not emp:
            continue
        first = firsts.get(r.employee)
        upd = {}
        ft = str(first)[11:16] if first else ""
        if (r.first_checkin or "") != ft:
            upd["first_checkin"] = ft
        note = "" if first else "chưa chấm công ngày này"
        if doc.counts_as_workday:
            if first:
                try:
                    if _mark_present(emp, day, first):
                        rep["present"].append(r.employee)
                except Exception:
                    frappe.log_error(title="holiday_work present %s %s" % (r.employee, day),
                                     message=frappe.get_traceback())
            _sla(r.employee, day)
        if days > 0 and not r.leave_ledger and (first or not doc.require_checkin):
            try:
                led, note = _credit_leave(emp, day, days)
            except Exception:
                led, note = None, "lỗi cộng phép, xem Error Log"
                frappe.log_error(title="holiday_work credit %s %s" % (r.employee, day),
                                 message=frappe.get_traceback())
            if led:
                upd["leave_ledger"] = led
                upd["leave_credited"] = days
                rep["credited"].append(r.employee)
        if r.leave_ledger or upd.get("leave_ledger"):
            note = ""
        if (r.status_note or "") != note:
            upd["status_note"] = note
        if upd:
            frappe.db.set_value("EC Holiday Work Member", r.name, upd, update_modified=False)
    frappe.logger("hr").info("holiday_work.apply %s" % rep)
    return rep


def daily():
    """Job 23:40 + 12:10: xu ly cac dot trong 7 ngay qua (cham cong muon, quy phep moi...)."""
    if not frappe.db.table_exists(DT):
        return
    today = getdate(nowdate())
    for n in frappe.get_all(DT, filters={"work_date": ["between", [add_days(today, -7), today]]},
                            pluck="name"):
        try:
            apply(n)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="holiday_work.daily %s" % n, message=frappe.get_traceback())
