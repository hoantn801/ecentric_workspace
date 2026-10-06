# Copyright (c) 2026, eCentric and contributors
"""Nhan vien "mac dinh du cong": khong cham cong, khong tinh SLA, bang cong tu du.

01/10/2026 - CnB: anh Lam (CEO) va hai nguoi khong dung ERP (bac Tran Nhan Tuan, bac Vu
Thi Linh) thang nao cung phai them tay vao bang cong. Hoan chot: bat mot o tren ho so
nhan vien (Employee.ec_full_cong) thi:
  - moi ngay lam viec (T2-T6, tru ngay le theo lich nghi) tu co Attendance "Present";
    ngay da co ban ghi (nghi phep, cham tay...) thi giu nguyen, khong ghi de;
  - khong sinh nghia vu SLA cham cong (sla/infrastructure/attendance_source.py);
  - khong nhac cham cong 08:30 / 09:30 (hr/checkin_reminder.py);
  - khong can chot cong thang (hr/timesheet_close/service.py).
Job 06:05 hang ngay quet tu ngay 1 thang TRUOC toi hom nay - nguoi moi bat co (hoac HR
tao ho so moi) la thang dang chot cung du cong luon. Chay lai khong nhan doi gi.

02/10/2026 - CnB tick o cho bac Tuan / bac Linh luc 11h ngay chot cong, ma job 06:05 da
chay roi -> phai doi toi hom sau. Nay: VUA BAT co (hook Employee.on_update) la ghi du cong
ngay, huy nghia vu SLA cham cong da sinh, va dong chot cong chua chot cua ho tu chuyen
"Da chot" (CnB chot thay) - nguoi du cong khong can chot (Hoan chot 02/10).
"""
import datetime

import frappe
from frappe.utils import getdate, nowdate

FIELD = "ec_full_cong"
LABEL = "Mặc định đủ công (không chấm công, không tính SLA)"
WORKDAYS = (0, 1, 2, 3, 4)


def ensure_field():
    """Tao Custom Field neu chua co. Goi tu patch - fixture sync chay SAU patch."""
    if frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": FIELD}):
        return False
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    create_custom_field("Employee", {
        "fieldname": FIELD, "label": LABEL, "fieldtype": "Check", "default": "0",
        "insert_after": "status",
        "description": "Bật cho người không chấm công: hệ thống tự ghi đủ công ngày làm việc, "
                       "không nhắc chấm công, không tính SLA chấm công, không cần chốt công.",
    })
    return True


def _has_field():
    try:
        return bool(frappe.db.has_column("Employee", FIELD))
    except Exception:
        return False


def employees():
    """Ten ban ghi cac nhan vien Active dang bat co. Khong co cot -> rong (an toan)."""
    if not _has_field():
        return set()
    return set(frappe.get_all("Employee", filters={"status": "Active", FIELD: 1},
                              pluck="name", limit_page_length=0))


def users():
    """user_id cua nhom tren - de module khac loc theo tai khoan."""
    if not _has_field():
        return set()
    return {u for u in frappe.get_all("Employee", filters={"status": "Active", FIELD: 1},
                                      pluck="user_id", limit_page_length=0) if u}


def is_full_cong(employee):
    return bool(employee) and employee in employees()


def _days(start, end):
    d, out = getdate(start), []
    while d <= getdate(end):
        out.append(d)
        d += datetime.timedelta(days=1)
    return out


def mark_range(start, end, only=None):
    """Ghi Attendance Present cho moi ngay lam viec con trong. -> report dict.
    `only`: chi nhung ho so nay (van phai dang bat co)."""
    from ecentric_workspace.sla.infrastructure import attendance_source as att
    report = {"tao": 0, "co_san": 0, "loi": []}
    names = employees()
    if only is not None:
        names = names & set(only)
    if not names:
        return report
    rows = frappe.get_all("Employee", filters={"name": ("in", list(names))},
                          fields=["name", "company", "holiday_list", "date_of_joining"],
                          limit_page_length=0)
    cache = {}
    for e in rows:
        hol = att._holidays_for(e, cache)
        have = {getdate(r) for r in frappe.get_all(
            "Attendance", filters={"employee": e.name, "docstatus": ("<", 2),
                                   "attendance_date": ("between", [str(start), str(end)])},
            pluck="attendance_date", limit_page_length=0)}
        for d in _days(start, end):
            if d.weekday() not in WORKDAYS or d in hol:
                continue
            if e.date_of_joining and d < getdate(e.date_of_joining):
                continue
            if d in have:
                report["co_san"] += 1
                continue
            sp = "ec_du_cong"
            try:
                frappe.db.savepoint(sp)
                doc = frappe.get_doc({"doctype": "Attendance", "employee": e.name,
                                      "attendance_date": d, "status": "Present",
                                      "company": e.company})
                doc.flags.ignore_permissions = True
                doc.insert(ignore_permissions=True)
                doc.submit()
                report["tao"] += 1
            except Exception:
                frappe.db.rollback(save_point=sp)
                report["loi"].append("%s %s" % (e.name, d))
                frappe.log_error(title="Du cong: khong ghi duoc %s %s" % (e.name, d),
                                 message=frappe.get_traceback())
    return report


def run_daily():
    """06:05 hang ngay: tu ngay 1 thang truoc toi hom nay."""
    today = getdate(nowdate())
    first_this = today.replace(day=1)
    start = (first_this - datetime.timedelta(days=1)).replace(day=1)
    rep = mark_range(start, today)
    try:
        rep["chot_cong"] = close_rows()
    except Exception:
        frappe.log_error(title="Du cong: tu chot cong loi", message=frappe.get_traceback())
    frappe.db.commit()
    if rep["loi"]:
        frappe.log_error(title="Du cong: %d ngay loi" % len(rep["loi"]), message=str(rep))
    return rep


def _window_start():
    today = getdate(nowdate())
    return (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1), today


def cancel_sla(user_ids):
    """Huy (Cancelled, KHONG xoa) nghia vu SLA cham cong da sinh cho nguoi du cong."""
    user_ids = [u for u in (user_ids or []) if u]
    if not user_ids:
        return 0
    names = frappe.get_all("EC SLA Obligation", filters={
        "obligation_type": "ATTENDANCE_DAY", "owner_user": ("in", user_ids),
        "status": ("!=", "Cancelled")}, pluck="name", limit_page_length=0)
    for n in names:
        frappe.db.set_value("EC SLA Obligation", n, {
            "status": "Cancelled", "is_breached": 0,
            "excluded_reason": "Mặc định đủ công - không tính SLA chấm công"},
            update_modified=False)
    return len(names)


def close_rows(only=None):
    """Dong chot cong chua chot cua nguoi du cong -> Closed, ghi la CnB/HR chot thay.
    Nguoi du cong khong chot cong (Hoan 02/10) - de dong Open thi leader / CnB phai bam
    thay va nguoi do hien la "chua chot" tren tab tong quan."""
    from ecentric_workspace.hr.timesheet_close import rules as R
    names = employees()
    if only is not None:
        names = names & set(only)
    if not names:
        return 0
    now = frappe.utils.now_datetime()
    rows = frappe.get_all("EC Timesheet Close", filters={
        "employee": ("in", list(names)), "status": ("!=", R.ST_CLOSED)},
        fields=["name", "status"], limit_page_length=0)
    for r in rows:
        vals = {"status": R.ST_CLOSED, "team_closed_at": now, "team_closed_by": "Administrator",
                "notes": "Mặc định đủ công - hệ thống tự chốt"}
        if r.status == R.ST_OPEN:
            vals.update({"member_closed_at": now, "member_closed_by": "Administrator",
                         "close_mode": R.MODE_HR})
        frappe.db.set_value("EC Timesheet Close", r.name, vals)
    return len(rows)


def on_employee_update(doc, method=None):
    """Hook Employee.on_update: vua bat co (hoac tao moi da bat) -> ghi du cong ngay, huy SLA
    cham cong, tu chot cong. Nuot moi loi: khong bao gio chan luu ho so."""
    try:
        if not int(doc.get(FIELD) or 0) or doc.get("status") != "Active":
            return
        before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
        if before is not None and int(before.get(FIELD) or 0):
            return
        start, today = _window_start()
        mark_range(start, today, only={doc.name})
        close_rows(only={doc.name})
        if doc.get("user_id"):
            cancel_sla([doc.user_id])
    except Exception:
        frappe.log_error(title="Du cong: hook ho so %s" % doc.get("name"), message=frappe.get_traceback())
