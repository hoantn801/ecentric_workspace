# Copyright (c) 2026, eCentric and contributors
"""Nhom "Cham cong": doc `Employee Checkin` -> nghia vu SLA.

KHONG SUA MOT DONG NAO trong trang `/ec-hr/attendance` hay luong cham cong. Giong
het cach lam voi bao cao tuan: nguon du lieu da day du, module SLA chi DOC.

LUAT LOAI TRU KHONG VIET LAI. `hr/checkin_reminder.py` da chay tren ban song va
da co dung bon luat can dung - chua vao lam, ngay le theo lich RIENG cua tung
nguoi, nghi phep da duyet, da cham roi. Viet lai se tao ra ban thu hai cua cung
mot luat, va tu ngay do hai ban se troi ra khoi nhau. Tep nay doc cung nhung
bang do.

NGHI PHEP DUYET HOI TO. Chu so huu chot 16/09: nguoi nghi that, don ve sau, thi
ngay do van phai duoc ghi nhan dung. Nen `sync` khong chi TAO nghia vu - moi lan
chay no con soat lai nhung ngay DA bi cham `Missed` ma bay gio da co phep duoc
duyet, va loai tru chung. Khong co buoc do thi mot phieu nghi duyet cham ba ngay
se de lai mot vet tru diem vinh vien, va nguoi bi tru khong co cach nao tu sua.

Chay lai bao nhieu lan cung ra mot ket qua: khoa chong trung la
`ATTENDANCE_DAY:<user>:Employee:<employee>:<ngay>:1`.
"""
import frappe
from frappe.utils import get_datetime, getdate

from ecentric_workspace.sla.application import obligation_service as obl
from ecentric_workspace.sla.constants import (
    DT_OBLIGATION, STATUS_EXCLUDED, STATUS_MISSED, STATUS_OPEN, TYPE_ATTENDANCE_DAY,
)
from ecentric_workspace.sla.domain import attendance_rules as ar

SRC_DOCTYPE = "Employee"
POLICY_CODE = "SLA-ATT-CHECKIN-10H"


def _employees():
    """Nhan vien dang lam, co tai khoan. Khong co `user_id` thi khong gan diem
    cho ai duoc - va dem ho vao se tao ra nhung dong nghia vu khong chu."""
    return frappe.get_all(
        "Employee", filters={"status": "Active", "user_id": ("is", "set")},
        fields=["name", "user_id", "employee_name", "department",
                "holiday_list", "date_of_joining", "company"],
        limit_page_length=0)


def _holidays_for(emp, cache):
    hl = emp.get("holiday_list")
    if not hl:
        return set()
    if hl not in cache:
        try:
            cache[hl] = {getdate(r["holiday_date"]) for r in frappe.get_all(
                "Holiday", filters={"parent": hl}, fields=["holiday_date"],
                limit_page_length=0)}
        except Exception:
            frappe.log_error(title="sla.attendance._holidays_for",
                             message=frappe.get_traceback())
            cache[hl] = set()
    return cache[hl]


def _leave_days(employee, start, end):
    """Cac ngay nghi phep DA DUYET, bung ra theo tung ngay."""
    try:
        rows = frappe.get_all("Leave Application", filters={
            "employee": employee, "status": "Approved", "docstatus": 1,
            "from_date": ("<=", end), "to_date": (">=", start),
        }, fields=["from_date", "to_date"], limit_page_length=0)
    except Exception:
        frappe.log_error(title="sla.attendance._leave_days",
                         message=frappe.get_traceback())
        return set()
    import datetime
    lo, hi, days = getdate(start), getdate(end), set()
    for r in rows:
        d, stop = max(getdate(r["from_date"]), lo), min(getdate(r["to_date"]), hi)
        while d <= stop:
            days.add(d)
            d += datetime.timedelta(days=1)
    return days


def _checkins(employee, start, end):
    """{ngay: moc cham SOM NHAT}. Lay som nhat chu khong phai muon nhat: nguoi
    cham 9:00 roi cham lai 14:00 van la cham dung gio."""
    try:
        rows = frappe.get_all("Employee Checkin", filters={
            "employee": employee, "time": ("between", [str(start) + " 00:00:00",
                                                       str(end) + " 23:59:59"]),
        }, fields=["time"], order_by="time asc", limit_page_length=0)
    except Exception:
        frappe.log_error(title="sla.attendance._checkins",
                         message=frappe.get_traceback())
        return {}
    out = {}
    for r in rows:
        d = getdate(r["time"])
        if d not in out:
            out[d] = r["time"]
    return out


# --------------------------------------------------------------------------- #
# Dong bo
# --------------------------------------------------------------------------- #
def _new_report():
    return {k: [] for k in ("mo", "dong", "loai_tru", "hoi_to_nghi_phep",
                            "bo_qua", "truoc_ngay_ap_dung", "loi")}


def _sync_employee(emp, start, end, hl_cache, report):
    days = ar.workdays_between(start, end, _holidays_for(emp, hl_cache))
    if not days:
        return
    leave = _leave_days(emp["name"], start, end)
    checkins = _checkins(emp["name"], start, end)
    user = emp["user_id"]

    for d in days:
        action, closed_at, reason = ar.decide(
            d, joined_on=emp.get("date_of_joining"),
            on_leave=(d in leave), first_checkin=checkins.get(d))
        if action == ar.ACT_SKIP:
            report["bo_qua"].append("%s %s (%s)" % (user, d, reason))
            continue

        opened_at = "%s 00:00:00" % d
        if obl.before_start(TYPE_ATTENDANCE_DAY, opened_at):
            report["truoc_ngay_ap_dung"].append("%s %s" % (user, d))
            continue

        name = obl.open_obligation(
            type_code=TYPE_ATTENDANCE_DAY, owner_user=user,
            source_doctype=SRC_DOCTYPE, source_name=emp["name"],
            source_detail=str(d), opened_at=opened_at,
            title="Ngày công %s" % d, policy_code=POLICY_CODE)
        if not name:
            continue

        if action == ar.ACT_EXCLUDE:
            _ensure_excluded(name, reason, report, user, d)
        elif action == ar.ACT_CLOSE:
            st = obl.close_obligation(name, get_datetime(closed_at))
            if st:
                report["dong"].append("%s %s -> %s" % (user, d, st))
        else:
            report["mo"].append("%s %s" % (user, d))


def _ensure_excluded(name, reason, report, user, day):
    """Loai tru mot ngay nghi phep - KE CA khi no da bi cham `Missed` tu truoc.

    Day la duong hoi to: phieu nghi duyet cham ba ngay thi lan chay hom nay phai
    go duoc vet tru diem hom kia. `exclude_obligation` co y cho phep loai tru mot
    dong da `Late`/`Missed` dung vi truong hop nay.
    """
    cur = frappe.db.get_value(DT_OBLIGATION, name, "status")
    if cur == STATUS_EXCLUDED:
        return
    if obl.exclude_obligation(name, reason):
        if cur == STATUS_MISSED:
            report["hoi_to_nghi_phep"].append("%s %s (gỡ Missed)" % (user, day))
        else:
            report["loai_tru"].append("%s %s" % (user, day))


def sync(start=None, end=None):
    """Dong bo mot khoang ngay. Mac dinh: 7 ngay gan nhat.

    Cua so 7 ngay du de bat ca ba viec: ngay hom nay, nhung ngay vua co nguoi
    cham bu, va nhung phieu nghi vua duoc duyet hoi to trong tuan.
    """
    end = getdate(end or frappe.utils.nowdate())
    start = getdate(start or frappe.utils.add_days(end, -7))
    report = _new_report()
    hl_cache = {}
    try:
        emps = _employees()
    except Exception:
        frappe.log_error(title="sla.attendance.sync", message=frappe.get_traceback())
        return report
    report["nhan_vien"] = len(emps)
    report["tu_ngay"], report["den_ngay"] = str(start), str(end)

    for emp in emps:
        sp = "sla_att"
        try:
            frappe.db.savepoint(sp)
        except Exception:
            sp = None
        try:
            _sync_employee(emp, start, end, hl_cache, report)
        except Exception:
            if sp:
                try:
                    frappe.db.rollback(save_point=sp)
                except Exception:
                    pass
            report["loi"].append(emp.get("user_id"))
            frappe.log_error(title="sla.attendance %s" % emp.get("user_id"),
                             message=frappe.get_traceback())
    return report


def backfill(start="2026-09-01", end=None):
    """Dung lai ngay cong tu dau thang 9 - moc chu so huu chot cho nhom nay."""
    return sync(start=start, end=end)


# --------------------------------------------------------------------------- #
# Do phu
# --------------------------------------------------------------------------- #
def coverage(period=None):
    """Ai KHONG co ngay cong nao trong ky. Gan nhu luon la nguoi thieu `user_id`
    hoac moi vao lam - nhung phai hien ra, vi khong co nghia vu thi khong bi do."""
    from ecentric_workspace.sla.application.scoreboard_service import current_period
    period = period or current_period()
    out = {"period": period, "co": 0, "khong_co": []}
    try:
        having = set(frappe.get_all(DT_OBLIGATION, filters={
            "period_month": period, "obligation_type": TYPE_ATTENDANCE_DAY},
            pluck="owner_user", limit_page_length=0))
        for e in _employees():
            if e["user_id"] in having:
                out["co"] += 1
            else:
                out["khong_co"].append("%s (%s)" % (e["user_id"],
                                                    e.get("department") or "không phòng ban"))
    except Exception:
        frappe.log_error(title="sla.attendance.coverage",
                         message=frappe.get_traceback())
    return out


def open_count():
    return frappe.db.count(DT_OBLIGATION, {"obligation_type": TYPE_ATTENDANCE_DAY,
                                           "status": STATUS_OPEN})
