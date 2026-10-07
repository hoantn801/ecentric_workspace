# Copyright (c) 2026, eCentric and contributors
"""Doc DB cho hai tab tong hop SLA / Phan bo cong viec tren /tong-quan#nhan-su.

Chi doc. Quyen chan o api._guard (HR_CARD_ROLES) TRUOC khi vao day: cac ham nay dung
frappe.get_all (bo qua DocPerm) de lay ca cong ty, nen tuyet doi khong goi tu cho khac.
Khong doc truong luong nao."""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.hr.overview import team_summary as TS

OBLIGATION = "EC SLA Obligation"
BW = "EC Brand Weight Request"
BW_DETAIL = "EC Brand Weight Request Detail"
_CAP = 20000
_PERIOD_CAP = 12


def _departments():
    rows = frappe.get_all("Department", fields=["name", "department_name", "manager_email"], limit_page_length=0)
    names = _user_names([r.manager_email for r in rows if r.manager_email])
    return {r.name: {"label": r.department_name or r.name, "manager": names.get(r.manager_email)} for r in rows}


def _user_names(users):
    users = [u for u in set(users) if u]
    if not users:
        return {}
    out = {u.user_id: u.employee_name for u in frappe.get_all(
        "Employee", filters={"user_id": ["in", users]}, fields=["user_id", "employee_name"],
        order_by="status asc", limit_page_length=0)}
    for u in frappe.get_all("User", filters={"name": ["in", [x for x in users if x not in out]]},
                            fields=["name", "full_name"], limit_page_length=0):
        out[u.name] = u.full_name or u.name
    return out


def sla_periods():
    from ecentric_workspace.sla.application import scoreboard_service
    return scoreboard_service.current_period(), scoreboard_service.periods()


def sla_summary(period):
    rows = frappe.get_all(OBLIGATION, filters={"period_month": period, "status": ("!=", "Cancelled")},
                          fields=["owner_user", "department", "group_key", "counts_toward_sla",
                                  "status", "due_at", "paused_seconds"],
                          limit_page_length=_CAP)
    if len(rows) >= _CAP:
        frappe.log_error(title="tong-quan sla bi cat", message="ky %s cham tran %d dong" % (period, _CAP))
    people = {}
    for e in frappe.get_all("Employee", filters={"status": "Active", "user_id": ["is", "set"]},
                            fields=["user_id", "employee_name", "department"], limit_page_length=0):
        people[e.user_id] = {"name": e.employee_name, "department": e.department, "active": True}
    missing = {r.owner_user for r in rows if r.owner_user and r.owner_user not in people}
    for u, n in _user_names(list(missing)).items():
        people[u] = {"name": n, "department": "", "active": False}
    data = TS.build_sla(rows, people, _departments(), period, now_datetime())
    data["truncated"] = len(rows) >= _CAP
    return data


def _prev(p):
    y, m = int(p[:4]), int(p[5:7])
    return "%04d-12" % (y - 1) if m == 1 else "%04d-%02d" % (y, m - 1)


def brand_periods():
    from ecentric_workspace.approval_center.features.brand_weight.application.period_service import default_period
    cur = default_period()
    first = frappe.get_all(BW, filters=[["period", ">", ""]], fields=["period"], order_by="period asc", limit=1)
    first = (first[0].period if first else cur) or cur
    out, p = [], cur
    for _ in range(_PERIOD_CAP):
        out.append(p)
        if p <= first:
            break
        p = _prev(p)
    return cur, out


def brand_summary(period):
    docs = frappe.get_all(BW, filters={"period": period},
                          fields=["name", "employee", "department", "creation", "approval_request"],
                          limit_page_length=0)
    reqs = [d.approval_request for d in docs if d.approval_request]
    st = {}
    waiting = {}
    if reqs:
        for r in frappe.get_all("EC Approval Request", filters={"name": ["in", reqs]},
                                fields=["name", "approval_status", "current_level"], limit_page_length=0):
            st[r.name] = r
        rows = frappe.db.sql(
            """select ap.approval_request, ap.approver
               from `tabEC Approval Request Approver` ap
               inner join `tabEC Approval Request` r on r.name = ap.approval_request
               where ap.approval_request in %(reqs)s and ap.status = 'Pending'
                 and r.approval_status = 'Pending' and ap.level_no = r.current_level""",
            {"reqs": tuple(reqs)}, as_dict=True)
        names = _user_names([r.approver for r in rows])
        for r in rows:
            waiting.setdefault(r.approval_request, []).append(names.get(r.approver) or r.approver)
    emp_names = {e.name: e.employee_name for e in frappe.get_all(
        "Employee", filters={"name": ["in", list({d.employee for d in docs if d.employee}) or [""]]},
        fields=["name", "employee_name"], limit_page_length=0)}
    full = []
    for d in docs:
        s = st.get(d.approval_request) or {}
        full.append({"name": d.name, "employee": d.employee, "employee_name": emp_names.get(d.employee),
                     "department": d.department, "creation": str(d.creation or ""),
                     "approval_request": d.approval_request,
                     "approval_status": s.get("approval_status"), "current_level": s.get("current_level")})
    details = {}
    if docs:
        for r in frappe.db.sql(
                """select parent, brand, weight from `tab%s` where parenttype = %%(pt)s and parent in %%(p)s""" % BW_DETAIL,
                {"pt": BW, "p": tuple(d.name for d in docs)}, as_dict=True):
            if r.brand and r.weight:
                details.setdefault(r.parent, {})[r.brand] = float(r.weight)
    labels = {b.name: (b.ec_brand_name or "").strip() or b.name
              for b in frappe.get_all("Brand", fields=["name", "ec_brand_name"], limit_page_length=0)}
    expected = [{"employee": e.name, "name": e.employee_name, "department": e.department}
                for e in frappe.get_all("Employee", filters={"status": "Active", "user_id": ["is", "set"]},
                                        fields=["name", "employee_name", "department"], limit_page_length=0)]
    return TS.build_brand(expected, full, details, waiting, labels, _departments(), period)


# ------------------------------------------------------------------ File tong hop cua CnB
def _company():
    return (frappe.defaults.get_global_default("company")
            or (frappe.get_all("Company", pluck="name", limit=1) or [None])[0])


def cnb_dashboard(period):
    """ec-cnb-dashboard-v1: file "Timesheet Thang N Dashboard" CnB tu ghep moi thang.
    Bang cong lay TU CHINH bao cao Monthly Attendance Sheet cua HRMS (cung ma P/H/L/A/HD/P/WO
    va 2 cot chot cong nhu khi CnB tu xuat) -> khong tu tinh lai cong o day."""
    from hrms.hr.report.monthly_attendance_sheet import monthly_attendance_sheet as MAS

    from ecentric_workspace.hr.overview import cnb_dashboard as CD
    from ecentric_workspace.hr.timesheet_close import report_columns as RC

    filters = frappe._dict(filter_based_on="Month", month=str(int(period[5:7])), year=period[:4],
                           company=_company(), summarized_view=0)
    res = MAS.execute(filters)
    closes = frappe.get_all("EC Timesheet Close", filters={"period_month": period},
                            fields=["employee", "status", "close_mode", "lead_user", "member_closed_at",
                                    "member_deadline", "team_closed_at", "lead_deadline"],
                            limit_page_length=0)
    res = RC.add_columns(res, {r.employee: r for r in closes})
    depts = _departments()
    emps = frappe.get_all("Employee", fields=["name", "department", "user_id"], order_by="status asc",
                          limit_page_length=0)
    dept_of = {e.name: (depts.get(e.department) or {}).get("label") or (e.department or "") for e in emps}
    emp_of_user = {}
    for e in emps:
        if e.user_id:
            emp_of_user.setdefault(e.user_id, e.name)
    days, ts = CD.timesheet_rows(res, dept_of)
    sla_groups, sla = CD.sla_rows(sla_summary(period), emp_of_user)
    bw_brands, bw = CD.brand_rows(brand_summary(period))
    return CD.filename(period), CD.build(period, days, ts, sla_groups, sla, bw_brands, bw)
