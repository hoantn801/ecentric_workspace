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
    DT_OBLIGATION, STATUS_CANCELLED, STATUS_EXCLUDED, STATUS_MISSED, STATUS_OPEN,
    TYPE_ATTENDANCE_DAY,
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


def _company_holiday_list(company, cache):
    """Holiday List mac dinh cua cong ty."""
    key = ("company", company or "")
    if key not in cache:
        try:
            cache[key] = frappe.db.get_value("Company", company,
                                             "default_holiday_list") if company else None
        except Exception:
            cache[key] = None
    return cache[key]


def _holidays_for(emp, cache):
    """Ngay nghi cua MOT nguoi. Khong co lich rieng thi lay lich mac dinh cua
    cong ty.

    Buoc du phong nay khong phai de cho chac. Do tren ban chay 17/09: 13/75 nhan
    vien khong duoc gan `holiday_list` nao - gan het la nguoi moi vao lam. Khong
    co buoc nay thi ho la nhom duy nhat bi cham diem vao ngay Quoc khanh 02/09,
    va ho cung la nhom it co kha nang len tieng nhat. Mot lo hong du lieu cua HR
    khong duoc phep tro thanh mot khoan tru diem.
    """
    hl = emp.get("holiday_list") or _company_holiday_list(emp.get("company"), cache)
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
                            "go_ngay_nghi", "bo_qua", "truoc_ngay_ap_dung", "loi")}


def _cancel_non_workdays(emp, start, end, days, report):
    """Go nhung ngay DA tao nghia vu nhung bay gio khong con la ngay lam viec.

    Duong sua chua, doi xung voi duong hoi to cua nghi phep. Khi HR gan lich
    nghi cho mot nguoi vi phai - hoac sua mot ngay le khai thieu - thi nhung
    nghia vu da tao cho ngay do phai bien mat, neu khong vet tru diem se nam lai
    vinh vien va khong ai go duoc.

    Dung `Cancelled` chu khong xoa: diem cua mot nguoi phai truy nguoc duoc.
    """
    want = {str(d) for d in days}
    try:
        rows = frappe.get_all(DT_OBLIGATION, filters={
            "obligation_type": TYPE_ATTENDANCE_DAY, "owner_user": emp["user_id"],
            "source_detail": ("between", [str(start), str(end)]),
            "status": ("not in", [STATUS_CANCELLED]),
        }, fields=["name", "source_detail"], limit_page_length=0)
    except Exception:
        frappe.log_error(title="sla.attendance._cancel_non_workdays",
                         message=frappe.get_traceback())
        return
    for r in rows:
        if r["source_detail"] in want:
            continue
        frappe.db.set_value(DT_OBLIGATION, r["name"], {
            "status": STATUS_CANCELLED, "is_breached": 0,
            "excluded_reason": "Ngày này không còn là ngày làm việc (lịch nghỉ đã cập nhật)",
        }, update_modified=False)
        report["go_ngay_nghi"].append("%s %s" % (emp["user_id"], r["source_detail"]))


def _sync_employee(emp, start, end, hl_cache, report):
    days = ar.workdays_between(start, end, _holidays_for(emp, hl_cache))
    _cancel_non_workdays(emp, start, end, days, report)
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
# --------------------------------------------------------------------------- #
# Duong THOI GIAN THUC
#
# `sync()` o tren chay mot lan moi dem. Giua hai lan chay do co mot lo hong that:
# han cham cong la 10:00, nen tu 10:00:01 den lan chay dem, mot nguoi DA cham
# cong dung gio van bi `effective_status` doc ra thanh `Missed` - vi nghia vu con
# `Open` va da qua han. Bang diem noi ho chua lam, trong khi ho lam roi.
#
# Do khong phai mot sai so nho: no dung voi CA CONG TY, MOI NGAY, trong khoang
# 14 tieng. Va no chi sai theo mot huong - luon lam diem nguoi ta xau di.
#
# `sync_one` la duong dong ngay: `Employee Checkin` vua duoc tao -> dong nghia vu
# cua dung nguoi do, dung ngay do. Da doi chieu tren ban song: `creation` cua
# Employee Checkin trung `time` toi tung mili-giay, tuc la ban ghi duoc tao ngay
# luc nguoi ta bam, khong phai may cham cong day ve theo lo. Nen "ngay" o day la
# ngay that.
#
# KHONG VIET LAI MOT LUAT NAO. Ham nay goi dung `_sync_employee` ma job dem goi,
# chi khac o cua so: mot nguoi, mot ngay. Hai duong vao, mot bo luat - neu khong
# thi se co ngay duong thoi gian thuc va duong ban dem noi hai ket qua khac nhau
# ve cung mot ngay cong.
# --------------------------------------------------------------------------- #
def _employee_one(employee):
    """Mot nhan vien theo ten ban ghi. Cung bo truong voi `_employees()`."""
    try:
        rows = frappe.get_all(
            "Employee", filters={"name": employee, "status": "Active",
                                 "user_id": ("is", "set")},
            fields=["name", "user_id", "employee_name", "department",
                    "holiday_list", "date_of_joining", "company"],
            limit_page_length=1)
    except Exception:
        frappe.log_error(title="sla.attendance._employee_one",
                         message=frappe.get_traceback())
        return None
    return rows[0] if rows else None


def sync_one(employee, day=None):
    """Dong bo DUNG mot nhan vien, DUNG mot ngay. Chay lai duoc.

    Tra ve `_new_report()` da dien, hoac `None` neu khong co gi de lam. Ben goi
    (hook cham cong) khong duoc phu thuoc vao gia tri tra ve.
    """
    day = getdate(day or frappe.utils.nowdate())
    emp = _employee_one(employee)
    if not emp:
        return None
    report = _new_report()
    report["nhan_vien"] = 1
    report["tu_ngay"] = report["den_ngay"] = str(day)
    # Savepoint rieng: neu mot ngay cong hong thi no khong duoc keo theo giao
    # dich dang chay cua ben goi. Voi hook cham cong, giao dich dang chay CHINH
    # LA lan cham cong cua nguoi dung.
    sp = "sla_att_one"
    try:
        frappe.db.savepoint(sp)
    except Exception:
        sp = None
    try:
        _sync_employee(emp, day, day, {}, report)
    except Exception:
        if sp:
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:
                pass
        report["loi"].append(emp.get("user_id"))
        frappe.log_error(title="sla.attendance.sync_one %s" % emp.get("user_id"),
                         message=frappe.get_traceback())
    return report
