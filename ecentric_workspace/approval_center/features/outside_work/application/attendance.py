# Copyright (c) 2026, eCentric and contributors
"""Outside Work duyet xong -> ngay lam viec ben ngoai co Attendance "Present".

05/10/2026 (Hoan): bao.nguyen di lam ben ngoai 24/09 (EC-OWRK-2026-00003, da duyet) nhung lich
cong / bang cong ERP (Monthly Attendance Sheet) ngay do TRONG: check-in luc 11:09 (qua cutoff)
nen khong co Attendance nao. Trang /ec-hr/attendance tu dem ngay outside la du cong tu 25/09,
nhung bang cong ERP va payroll chi doc Attendance -> phai co ban ghi that.

Luat (Hoan chot: "outside work thi van nen la present"):
  - moi ngay T2-T6 khong phai ngay nghi (lich nghi cua nhan vien / cong ty) trong
    [start_date, end_date], tu ngay vao lam;
  - ngay CHUA co Attendance (docstatus < 2) -> tao + submit "Present";
  - ngay DA co ban ghi (nghi phep, cham tay, Present...) -> giu nguyen, khong ghi de;
  - SLA cham cong: ngay outside duoc loai tru (sla attendance_source._outside_days), ke ca
    hoi to cho ngay da bi cham tre;
  - chi ngay DA QUA (< hom nay): ngay hom nay / tuong lai de check-in tu ghi nhu thuong, HRMS
    cung khong cho tao Attendance ngay tuong lai. Job 06:15 hang ngay quet phieu da duyet tu
    ngay 1 thang truoc -> phieu duyet truoc cho ngay sau van duoc ghi khi ngay do qua.
Moi ngay mot savepoint: mot ngay loi khong lam hong ca phieu. Chay lai khong nhan doi.
"""
import datetime

import frappe
from frappe.utils import getdate, nowdate

BUSINESS_DT = "EC Outside Work Request"
WORKDAYS = (0, 1, 2, 3, 4)


def _days(start, end):
    d, out = getdate(start), []
    end = getdate(end)
    while d <= end:
        out.append(d)
        d += datetime.timedelta(days=1)
    return out


def plan_days(start, end, holidays, have, doj=None, before=None):
    """Thuan: ngay nao can tao Attendance. holidays/have = set ngay (date). `before`: chi
    lay ngay < before (mac dinh khong gioi han)."""
    out = []
    before = getdate(before) if before else None
    for d in _days(start, end):
        if d.weekday() not in WORKDAYS or d in holidays or d in have:
            continue
        if before and d >= before:
            continue
        if doj and d < getdate(doj):
            continue
        out.append(d)
    return out


def mark_present(name):
    """-> {'tao': n, 'loi': [...]} cho mot phieu Outside Work (phai dang Approved)."""
    from ecentric_workspace.sla.infrastructure import attendance_source as att
    rep = {"tao": 0, "loi": []}
    doc = frappe.db.get_value(BUSINESS_DT, name, ["employee", "start_date", "end_date", "approval_request"],
                              as_dict=True)
    if not doc or not doc.employee or not doc.start_date:
        return rep
    st = doc.approval_request and frappe.db.get_value("EC Approval Request", doc.approval_request,
                                                      "approval_status")
    if st != "Approved":
        return rep
    emp = frappe.db.get_value("Employee", doc.employee,
                              ["name", "company", "holiday_list", "date_of_joining"], as_dict=True)
    if not emp:
        return rep
    end = doc.end_date or doc.start_date
    hol = att._holidays_for(emp, {})
    have = {getdate(d) for d in frappe.get_all(
        "Attendance", filters={"employee": emp.name, "docstatus": ("<", 2),
                               "attendance_date": ("between", [str(doc.start_date), str(end)])},
        pluck="attendance_date", limit_page_length=0)}
    for d in plan_days(doc.start_date, end, hol, have, emp.date_of_joining, before=nowdate()):
        sp = "ec_outside_present"
        try:
            frappe.db.savepoint(sp)
            a = frappe.get_doc({"doctype": "Attendance", "employee": emp.name, "attendance_date": d,
                                "status": "Present", "company": emp.company})
            a.flags.ignore_permissions = True
            a.insert(ignore_permissions=True)
            a.submit()
            a.add_comment("Comment", "Làm việc bên ngoài đã duyệt: %s" % name)
            rep["tao"] += 1
        except Exception:
            frappe.db.rollback(save_point=sp)
            rep["loi"].append(str(d))
            frappe.log_error(title="Outside work: khong ghi duoc cong %s %s" % (emp.name, d),
                             message=frappe.get_traceback())
    # SLA cham cong: ngay outside da bi cham "tre" (check-in muon / khong check-in) -> loai tru
    # hoi to (sync_leave dong bo lai dung khoang ngay, tu nuot loi).
    try:
        att.sync_leave(emp.name, doc.start_date, end)
    except Exception:
        frappe.log_error(title="Outside work: sla sync %s" % name, message=frappe.get_traceback())
    return rep


def on_final_approval(name):
    """Handler cua engine (transitions._FULFILLMENT_HANDLERS). Nuot loi: duyet phieu khong
    bao gio hong vi buoc ghi cong."""
    try:
        return mark_present(name)
    except Exception:
        frappe.log_error(title="Outside work: on_final_approval %s" % name, message=frappe.get_traceback())
        return None


def backfill(since="2026-09-01"):
    """Ghi cong cho moi phieu da duyet co ngay tu `since` (patch chay mot lan)."""
    out = {"phieu": 0, "tao": 0, "loi": []}
    rows = frappe.db.sql(
        """select w.name from `tab%s` w inner join `tabEC Approval Request` a on a.name = w.approval_request
           where a.approval_status = 'Approved' and ifnull(w.end_date, w.start_date) >= %%s""" % BUSINESS_DT,
        (since,))
    for (name,) in rows:
        r = mark_present(name)
        out["phieu"] += 1
        out["tao"] += r["tao"]
        out["loi"] += r["loi"]
    return out


def run_daily():
    """Cron 06:15: phieu da duyet tu ngay 1 thang truoc - ghi cong ngay vua qua."""
    today = getdate(nowdate())
    since = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    out = backfill(str(since))
    frappe.db.commit()
    if out["loi"]:
        frappe.log_error(title="Outside work: %d ngay loi" % len(out["loi"]), message=str(out))
    return out
