# Copyright (c) 2026, eCentric and contributors
"""Chot cong thang - phan doc/ghi DB. Quy tac thuan o rules.py.

Mot dong `EC Timesheet Close` cho moi nhan vien / ky:
    Open           -> chua ai chot
    Member Closed  -> nhan vien da tu chot (khoa phia nhan vien)
    Closed         -> leader / CnB / HR da chot team (khoa han)
Khoa phia nhan vien duoc cac Server Script ec_hr_attendance_appeal / ec_hr_late_explain
/ ec_hr_leave_apply doc thang tu bang nay (ec-tsclose-lock-v1).

SLA: bang nay giu du moc (han + luc chot + ai chot) de module SLA doc MOT CHIEU va
cham diem / bu nguoc sau, giong cach `weekly_source` doc Weekly Team Update.
"""
import datetime as _dt

import frappe
from frappe.utils import get_datetime, getdate, now_datetime

from ecentric_workspace.hr.timesheet_close import rules as R

DT = "EC Timesheet Close"
HR_ROLES = ("HR Manager", "HR User", "EC CnB")
GROUP_TEAM = "team"
GROUP_NOLEAD = "nolead"


# ------------------------------------------------------------------ helpers
def _company_holidays(period):
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    hl = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
    if not hl:
        return []
    first = R.next_period_first_day(period)
    rows = frappe.db.sql("select holiday_date from `tabHoliday` where parent=%s and holiday_date between %s and %s",
                         (hl, first, first + _dt.timedelta(days=20)))
    return [r[0] for r in rows]


def deadlines(period):
    return R.deadlines(period, _company_holidays(period))


def _is_hr(user):
    if user == "Administrator":
        return True
    return bool(frappe.db.sql("select 1 from `tabHas Role` where parent=%s and parenttype='User' and role in %s limit 1",
                              (user, HR_ROLES)))


def _lead_map():
    """employee -> user cua quan ly truc tiep (chi khi quan ly con lam va tai khoan con bat)."""
    rows = frappe.db.sql("""
        select e.name, m.user_id
        from `tabEmployee` e
        left join `tabEmployee` m on m.name = e.reports_to and m.status = 'Active'
        left join `tabUser` u on u.name = m.user_id and u.enabled = 1
        where e.status = 'Active' and u.name is not null""")
    return {r[0]: r[1] for r in rows}


def _employees(period):
    first, last = R.period_bounds(period)
    return frappe.db.sql("""
        select name, employee_name, user_id, department
        from `tabEmployee`
        where status = 'Active' and (date_of_joining is null or date_of_joining <= %s)""",
                         (last,), as_dict=True)


# ------------------------------------------------------------------ rows
def ensure_rows(period):
    """Sinh / lam moi dong cua ky. Chay lai bao nhieu lan cung ra mot ket qua."""
    if not R.applies(period):
        return 0
    m_due, l_due = deadlines(period)
    leads = _lead_map()
    have = {r.employee: r for r in frappe.get_all(
        DT, filters={"period_month": period}, fields=["name", "employee", "status", "lead_user"])}
    made = 0
    # 01/10/2026: nguoi "mac dinh du cong" (hr/full_cong.py) khong can chot cong - khong
    # sinh dong moi cho ho. Dong da co tu truoc thi de nguyen (CnB/HR chot thay).
    try:
        from ecentric_workspace.hr import full_cong
        no_close = full_cong.employees()
    except Exception:
        no_close = set()
    for e in _employees(period):
        if e.name in no_close and e.name not in have:
            continue
        lead = leads.get(e.name) or None
        if lead == e.user_id:
            lead = None
        row = have.get(e.name)
        if row:
            # Doi quan ly giua ky: dong CHUA chot di theo quan ly moi.
            if row.status != R.ST_CLOSED and (row.lead_user or None) != lead:
                frappe.db.set_value(DT, row.name, "lead_user", lead, update_modified=False)
            continue
        doc = frappe.get_doc({
            "doctype": DT, "employee": e.name, "employee_name": e.employee_name,
            "user": e.user_id, "department": e.department, "period_month": period,
            "status": R.ST_OPEN, "lead_user": lead,
            "member_deadline": m_due, "lead_deadline": l_due,
        })
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        made += 1
    return made


def ensure_current():
    """Cron 00:05 hang ngay: mo ky ngay khi cua so chot mo (00:00 ngay 1)."""
    now = now_datetime()
    period = R.prev_period(now)
    if R.window_open(period, now):
        return ensure_rows(period)
    return 0


def is_locked(employee, period):
    return bool(frappe.db.exists(DT, {"employee": employee, "period_month": period,
                                      "status": ("in", R.LOCKED_STATES)}))


# ------------------------------------------------------------------ pending
def _pending(employees, period):
    """employee -> {'appeal': n, 'late': n, 'leave': {approver: n}}"""
    out = {e: {"appeal": 0, "late": 0, "leave": {}} for e in employees}
    if not employees:
        return out
    first, last = R.period_bounds(period)
    emps = tuple(employees)
    for emp, n in frappe.db.sql("""
            select employee, count(*) from `tabAttendance Request`
            where employee in %s and docstatus = 0 and ifnull(ec_appeal_status, 'Open') = 'Open'
              and from_date <= %s and to_date >= %s group by employee""", (emps, last, first)):
        out[emp]["appeal"] = n
    for emp, n in frappe.db.sql("""
            select employee, count(*) from `tabAttendance`
            where employee in %s and docstatus < 2 and ec_late_status = 'Open'
              and attendance_date between %s and %s group by employee""", (emps, first, last)):
        out[emp]["late"] = n
    for emp, appr, n in frappe.db.sql("""
            select employee, leave_approver, count(*) from `tabLeave Application`
            where employee in %s and docstatus = 0 and status = 'Open'
              and from_date <= %s and to_date >= %s group by employee, leave_approver""", (emps, last, first)):
        out[emp]["leave"][appr or ""] = n
    return out


def _blocking(p, closer, hr_mode):
    """Viec dang cho CHINH nguoi chot xu ly. Giai trinh (thieu cong / di muon) do
    quan ly truc tiep hoac HR duyet -> luon tinh. Don nghi chi tinh khi nguoi chot
    la nguoi duyet cua don (don dang o buoc Nhan su khong chan leader)."""
    n = p["appeal"] + p["late"]
    for appr, c in p["leave"].items():
        if hr_mode or appr == closer:
            n += c
    return n


# ------------------------------------------------------------------ state
def _row_dict(r, p=None, closer=None, hr_mode=False):
    d = {"employee": r.employee, "name": r.employee_name, "status": r.status,
         "member_closed_at": str(r.member_closed_at or "")[:16],
         "close_mode": r.close_mode or "",
         "team_closed_at": str(r.team_closed_at or "")[:16]}
    if p is not None:
        d["blocking"] = _blocking(p, closer, hr_mode)
        d["pending_total"] = p["appeal"] + p["late"] + sum(p["leave"].values())
    return d


def _group(period, rows, closer, hr_mode, key, title, l_due):
    pend = _pending([r.employee for r in rows if r.status != R.ST_CLOSED], period)
    members = [_row_dict(r, pend.get(r.employee, {"appeal": 0, "late": 0, "leave": {}}), closer, hr_mode)
               for r in rows]
    members.sort(key=lambda m: (m["status"] == R.ST_CLOSED, m["name"] or ""))
    open_rows = [m for m in members if m["status"] != R.ST_CLOSED]
    blocking = sum(m.get("blocking", 0) for m in open_rows)
    closed_at = max((m["team_closed_at"] for m in members), default="")
    return {"key": key, "title": title, "members": members, "count": len(members),
            "open": len(open_rows), "blocking": blocking,
            "closed": not open_rows, "closed_at": closed_at if not open_rows else "",
            "can_close": bool(open_rows) and blocking == 0, "lead_deadline": str(l_due)[:16]}


def _fields():
    return ["name", "employee", "employee_name", "status", "lead_user", "member_closed_at",
            "close_mode", "team_closed_at", "member_deadline", "lead_deadline"]


def get_state(user):
    now = now_datetime()
    period = R.prev_period(now)
    if not R.window_open(period, now):
        return {"active": False}
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if emp and not frappe.db.exists(DT, {"employee": emp, "period_month": period}):
        ensure_rows(period)
    m_due, l_due = deadlines(period)
    show_until = m_due.date()
    y, m = period.split("-")
    out = {"active": True, "period": period, "label": "tháng %d/%s" % (int(m), y),
           "member_deadline": str(m_due)[:16], "lead_deadline": str(l_due)[:16],
           "now": str(now)[:16], "me": None, "groups": []}

    if emp:
        r = frappe.get_all(DT, filters={"employee": emp, "period_month": period}, fields=_fields())
        if r:
            p = _pending([emp], period)[emp]
            me = _row_dict(r[0])
            me["pending_total"] = p["appeal"] + p["late"] + sum(p["leave"].values())
            me["late"] = (me["status"] == R.ST_OPEN and now > m_due)
            out["me"] = me

    team = frappe.get_all(DT, filters={"period_month": period, "lead_user": user}, fields=_fields())
    if team:
        out["groups"].append(_group(period, team, user, False, GROUP_TEAM, "Team của bạn", l_due))
    if _is_hr(user):
        nolead = frappe.get_all(DT, filters={"period_month": period, "lead_user": ("is", "not set")},
                                fields=_fields())
        if nolead:
            out["groups"].append(_group(period, nolead, user, True, GROUP_NOLEAD,
                                        "Không có quản lý trực tiếp (CnB / HR chốt thay)", l_due))

    today = now.date()
    me_done = (not out["me"]) or out["me"]["status"] != R.ST_OPEN
    groups_done = all(g["closed"] for g in out["groups"])
    out["show"] = not (me_done and groups_done and today > show_until)
    return out


# ------------------------------------------------------------------ actions
def close_self(user):
    now = now_datetime()
    period = R.prev_period(now)
    if not R.window_open(period, now):
        frappe.throw("Chưa đến kỳ chốt công.")
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not emp:
        frappe.throw("Không tìm thấy hồ sơ nhân viên của bạn.")
    if not frappe.db.exists(DT, {"employee": emp, "period_month": period}):
        ensure_rows(period)
    name = frappe.db.get_value(DT, {"employee": emp, "period_month": period}, "name")
    row = frappe.get_doc(DT, name)
    if row.status != R.ST_OPEN:
        return {"status": row.status, "already": True}
    row.status = R.ST_MEMBER
    row.member_closed_at = now
    row.member_closed_by = user
    row.close_mode = R.MODE_SELF
    row.flags.ignore_permissions = True
    row.save(ignore_permissions=True)
    return {"status": row.status, "member_closed_at": str(now)[:16]}


def close_team(user, group):
    now = now_datetime()
    period = R.prev_period(now)
    if not R.window_open(period, now):
        frappe.throw("Chưa đến kỳ chốt công.")
    hr_mode = group == GROUP_NOLEAD
    if hr_mode:
        if not _is_hr(user):
            frappe.throw("Chỉ CnB / HR chốt thay cho người không có quản lý trực tiếp.")
        filters = {"period_month": period, "lead_user": ("is", "not set")}
    else:
        filters = {"period_month": period, "lead_user": user}
    rows = [r for r in frappe.get_all(DT, filters=filters, fields=_fields()) if r.status != R.ST_CLOSED]
    if not rows:
        return {"closed": 0, "already": True}
    pend = _pending([r.employee for r in rows], period)
    stuck = [(r.employee_name, _blocking(pend[r.employee], user, hr_mode)) for r in rows]
    stuck = [s for s in stuck if s[1]]
    if stuck:
        frappe.throw("Còn việc đang chờ bạn duyệt trong %s: %s. Duyệt hoặc từ chối hết rồi chốt lại."
                     % ("tháng " + period[5:7].lstrip("0") + "/" + period[:4],
                        ", ".join("%s (%d)" % s for s in stuck)))
    return _close_rows(rows, user, R.MODE_HR if hr_mode else R.MODE_LEAD, now)


def _close_rows(rows, user, mode, now):
    for r in rows:
        doc = frappe.get_doc(DT, r.name)
        if doc.status == R.ST_OPEN:
            doc.member_closed_at = now
            doc.member_closed_by = user
            doc.close_mode = mode
        doc.status = R.ST_CLOSED
        doc.team_closed_at = now
        doc.team_closed_by = user
        doc.flags.ignore_permissions = True
        doc.save(ignore_permissions=True)
    return {"closed": len(rows), "team_closed_at": str(now)[:16]}


def close_for_lead(user, lead_user):
    """02/10/2026 - CnB: CnB / HR chot thay MOT team khi leader chua chot (vd anh Lam chua
    chot cho cac truong phong). Cung luat voi leader: con giai trinh / don nghi chua xu ly
    trong ky thi KHONG chot - nhung tinh theo che do HR (moi don deu tinh, vi CnB / HR duyet
    duoc giai trinh, con don nghi cho leader thi CnB nhac leader hoac duyet o buoc HR)."""
    now = now_datetime()
    period = R.prev_period(now)
    if not R.window_open(period, now):
        frappe.throw("Chưa đến kỳ chốt công.")
    if not _is_hr(user):
        frappe.throw("Chỉ CnB / HR được chốt thay cho leader.", frappe.PermissionError)
    if not lead_user:
        frappe.throw("Thiếu leader cần chốt thay.")
    rows = [r for r in frappe.get_all(DT, filters={"period_month": period, "lead_user": lead_user},
                                      fields=_fields()) if r.status != R.ST_CLOSED]
    if not rows:
        return {"closed": 0, "already": True}
    pend = _pending([r.employee for r in rows], period)
    stuck = [(r.employee_name, _blocking(pend[r.employee], user, True)) for r in rows]
    stuck = [s for s in stuck if s[1]]
    if stuck:
        frappe.throw("Còn giải trình / đơn nghỉ chưa xử lý trong %s: %s. Xử lý hết rồi chốt thay lại."
                     % ("tháng " + period[5:7].lstrip("0") + "/" + period[:4],
                        ", ".join("%s (%d)" % s for s in stuck)))
    return _close_rows(rows, user, R.MODE_HR, now)


# ------------------------------------------------------------------ HR overview
OVERVIEW_ROLES = ("System Manager", "HR Manager", "HR User", "EC CnB")


def can_overview(user):
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & set(OVERVIEW_ROLES))


def _names(users):
    users = [u for u in users if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name for r in frappe.get_all(
        "User", filters={"name": ("in", users)}, fields=["name", "full_name"])}


def overview(user):
    """Tab 'Chot cong' trong /tong-quan#nhan-su: tien do theo phong ban. Chi ten + trang thai,
    khong so lieu cong / luong."""
    now = now_datetime()
    period = R.prev_period(now)
    if not R.window_open(period, now):
        nxt = R.period_of(now)
        m_due, l_due = deadlines(nxt)
        return {"active": False, "period": nxt, "label": "tháng %d/%s" % (int(nxt[5:7]), nxt[:4]),
                "opens": str(R.next_period_first_day(nxt)), "member_deadline": str(m_due)[:16],
                "lead_deadline": str(l_due)[:16]}
    ensure_rows(period)
    m_due, l_due = deadlines(period)
    rows = frappe.get_all(DT, filters={"period_month": period}, fields=_fields() + ["department", "user"])
    depts = {d.name: d for d in frappe.get_all("Department", fields=["name", "department_name", "manager_email"],
                                                limit_page_length=0)}
    names = _names(list({r.lead_user for r in rows} | {d.manager_email for d in depts.values()}))
    groups = {}
    for r in rows:
        g = groups.setdefault(r.department or "", {"members": []})
        g["members"].append(r)
    out = []
    for key, g in groups.items():
        ms = g["members"]
        d = depts.get(key) or {}
        leads = sorted({r.lead_user for r in ms if r.lead_user and r.status != R.ST_CLOSED})
        closed = sum(1 for r in ms if r.status == R.ST_CLOSED)
        self_closed = sum(1 for r in ms if r.member_closed_at and r.close_mode == R.MODE_SELF)
        state = "done" if closed == len(ms) else ("partial" if closed or self_closed else "none")
        out.append({
            "department": key, "label": (d.get("department_name") if d else "") or key or "Chưa gán phòng",
            "manager": names.get(d.get("manager_email")) if d else None,
            "leads_pending": [names.get(u, u) for u in leads],
            "total": len(ms), "closed": closed, "self_closed": self_closed, "state": state,
            "member_only": sum(1 for r in ms if r.status == R.ST_MEMBER),
            "members": sorted([{"name": r.employee_name, "status": r.status, "close_mode": r.close_mode or "",
                                "member_closed_at": str(r.member_closed_at or "")[:16],
                                "lead": names.get(r.lead_user) if r.lead_user else "CnB / HR chốt thay"}
                               for r in ms], key=lambda x: (x["status"] == R.ST_CLOSED, x["name"] or "")),
        })
    out.sort(key=lambda x: ({"none": 0, "partial": 1, "done": 2}[x["state"]], x["label"]))
    # 02/10: CnB chot thay theo leader - moi leader con nguoi chua chot (Closed) trong team.
    by_lead = {}
    for r in rows:
        if r.lead_user and r.status != R.ST_CLOSED:
            by_lead.setdefault(r.lead_user, []).append(r)
    leads = sorted([{"lead_user": u, "name": names.get(u, u), "open": len(ms),
                     "self_closed": sum(1 for r in ms if r.status == R.ST_MEMBER),
                     "members": sorted(r.employee_name or "" for r in ms)}
                    for u, ms in by_lead.items()], key=lambda x: (-x["open"], x["name"] or ""))
    tot = len(rows)
    return {"active": True, "period": period, "label": "tháng %d/%s" % (int(period[5:7]), period[:4]),
            "member_deadline": str(m_due)[:16], "lead_deadline": str(l_due)[:16], "now": str(now)[:16],
            "stats": {"total": tot, "closed": sum(1 for r in rows if r.status == R.ST_CLOSED),
                      "self_closed": sum(1 for r in rows if r.member_closed_at and r.close_mode == R.MODE_SELF),
                      "open": sum(1 for r in rows if r.status == R.ST_OPEN)},
            "departments": out, "leads": leads, "can_close_for_lead": _is_hr(user)}
