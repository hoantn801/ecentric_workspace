# Copyright (c) 2026, eCentric and contributors
"""SLA tinh bang NGAY LAM VIEC cho cac luong HR (23/11/2026).

Hai loai han:
  1. Han CO DINH theo cap ("CnB/HR duyet trong 2 ngay LV"): mot EC Approval SLA Policy gio hanh
     chinh = so ngay x 8 gio tren lich EC_STANDARD_9_18 (T2-T6 9-12, 13-18 = 8 gio). Engine tu tinh
     due_at luc mo cap (transitions.resolve_sla). `ensure_policy` tao/cap nhat policy - chi goi tu
     setup/patch, idempotent.
  2. Han THEO NGAY CUA PHIEU ("moi nhom xong truoc ngay onboard 1 ngay LV", "han = ngay lam viec
     cuoi"): khong bieu dien duoc bang policy. Feature tinh ngay roi `dat_han_cap` ghi vao dong
     EC Approval Request Level cua phieu (due_at - stepper hien "Han", bao cao doc `due_at`) + ToDo.

AN TOAN: resolve_sla NEM LOI neu policy gio hanh chinh khong tim duoc Holiday List - va loi do
chan viec GUI phieu. Vi vay `ensure_policy` ghim Holiday List mac dinh cua cong ty vao policy; khong
tim duoc Holiday List hoac lich thi KHONG tao policy (tra None, ben goi bo SLA + canh bao).

Ham thuan (khong cham DB) o duoi cung de test duoc: tru_ngay_lam_viec."""
import datetime as _dt

import frappe

CALENDAR_CODE = "EC_STANDARD_9_18"
GIO_MOT_NGAY = 8
_WEEK = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _company_holiday_list():
    from ecentric_workspace.approval_center.shared.workflow import holidays as hol
    company = (frappe.defaults.get_global_default("company")
               or frappe.db.get_single_value("Global Defaults", "default_company"))
    return hol.resolve_holiday_list(company=company) if company else None


def _ensure_calendar():
    if frappe.db.exists("EC Approval Business Calendar", CALENDAR_CODE):
        return CALENDAR_CODE
    cal = frappe.new_doc("EC Approval Business Calendar")
    cal.calendar_code = CALENDAR_CODE
    cal.calendar_name = "eCentric Standard Working Calendar"
    cal.active = 1
    for d in _WEEK:
        cal.append("working_periods", {"weekday": d, "start_time": "09:00:00", "end_time": "12:00:00"})
        cal.append("working_periods", {"weekday": d, "start_time": "13:00:00", "end_time": "18:00:00"})
    cal.save(ignore_permissions=True)
    return CALENDAR_CODE


def policy_code(days):
    return "HR_%s_NGAY_LV" % int(days)


def ensure_policy(days, rep=None):
    """-> ma policy, hoac None neu khong an toan de gan (thieu Holiday List). Khong commit."""
    code = policy_code(days)
    hl = _company_holiday_list()
    if not hl:
        if rep is not None:
            rep.setdefault("warnings", []).append(
                "SLA %s: công ty chưa có Holiday List mặc định - KHÔNG gắn SLA (gắn vào sẽ chặn gửi phiếu)."
                % code)
        return None
    cal = _ensure_calendar()
    pol = frappe.get_doc("EC Approval SLA Policy", code) if frappe.db.exists(
        "EC Approval SLA Policy", code) else frappe.new_doc("EC Approval SLA Policy")
    if not pol.policy_code:
        pol.policy_code = code
    pol.policy_name = "HR %s ngày làm việc" % int(days)
    pol.duration_hours = int(days) * GIO_MOT_NGAY
    pol.use_business_hours = 1
    pol.business_calendar = cal
    pol.holiday_list = hl
    pol.active = 1
    pol.save(ignore_permissions=True)
    return code


def ngay_le():
    from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec as nlv
    return nlv.ngay_le_cong_ty()


def dat_han_cap(request_name, level_no, han_ngay, gio="18:00:00"):
    """Ghi han (cuoi ngay lam viec `han_ngay`) vao cap `level_no` cua phieu + ToDo dang mo cua cap.
    Khong doi trang thai gi. Loi -> Error Log, khong nem (han la thong tin phu, khong chan luong)."""
    try:
        if not (request_name and han_ngay):
            return None
        due = "%s %s" % (han_ngay, gio)
        rl = frappe.db.get_value("EC Approval Request Level",
                                 {"approval_request": request_name, "level_no": level_no}, "name")
        if not rl:
            return None
        frappe.db.set_value("EC Approval Request Level", rl, "due_at", due, update_modified=False)
        req = frappe.db.get_value("EC Approval Request", request_name,
                                  ["reference_doctype", "reference_name"], as_dict=True)
        if req:
            for td in frappe.get_all("ToDo", filters={"reference_type": req.reference_doctype,
                                                       "reference_name": req.reference_name,
                                                       "status": "Open"}, pluck="name"):
                frappe.db.set_value("ToDo", td, "date", str(han_ngay), update_modified=False)
        return due
    except Exception:
        frappe.log_error(title="sla_ngay_lam_viec.dat_han_cap %s" % request_name,
                         message=frappe.get_traceback())
        return None


# ----------------------------------------------------------------------------- ham thuan
def la_ngay_lam_viec(d, le=()):
    return d.weekday() < 5 and d not in le


def tru_ngay_lam_viec(den_ngay, so_ngay, le=()):
    """Ngay lam viec thu `so_ngay` TRUOC `den_ngay` (khong tinh chinh den_ngay)."""
    d, n = den_ngay, int(so_ngay or 0)
    while n > 0:
        d -= _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, le):
            n -= 1
    return d


def cong_ngay_lam_viec(tu_ngay, so_ngay, le=()):
    d, n = tu_ngay, int(so_ngay or 0)
    while n > 0:
        d += _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, le):
            n -= 1
    return d


def dem_ngay_lam_viec(tu_ngay, den_ngay, le=()):
    """So ngay lam viec d voi tu_ngay < d <= den_ngay."""
    n, d = 0, tu_ngay
    while d < den_ngay:
        d += _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, le):
            n += 1
    return n
