"""PM v2 - Worktime / Timesheet services (Day 2 item 4).

Uses NATIVE ERPNext `Timesheet` + child `Timesheet Detail` (the `time_logs`
table). No custom DocType, no realtime timer. Permission enforced in this PM
service layer (require_pm_access + can_view_task/project), same model as the
other PM services.

Each log = one Draft Timesheet with a single time_logs row referencing the Task.
Total hours are summed by the service (we do NOT rely on native submit/rollup,
so Timesheets stay editable as Draft). Audit trail is native (owner/creation).

Required-field handling (reported):
  - Timesheet.company    : resolved from Project.company -> user default ->
                           Global Defaults.default_company; throws if none.
  - Timesheet.employee   : set from Employee.user_id if it exists (optional).
  - Timesheet Detail.activity_type : set to an existing Activity Type if any
                           (some ERPNext versions make it mandatory).
  - from_time + hours    : provided by caller. billing flags left default (0).
"""

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm


def _company_for(project):
    company = frappe.db.get_value("Project", project, "company") if project else None
    if not company:
        company = frappe.defaults.get_user_default("company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    return company


def _employee_for(user):
    return frappe.db.get_value("Employee", {"user_id": user}, "name")


def _default_activity_type():
    return frappe.db.get_value("Activity Type", {}, "name")


def _create_timesheet(user, task, project, hours, description=None, from_time=None):
    """Shared helper: create one Draft Timesheet (single time_log) for a Task.

    Used by manual log AND by the timer Stop. Returns the Timesheet name.
    """
    company = _company_for(project)
    if not company:
        frappe.throw(_("No Company found. Set Project.company or a default Company."))
    if not from_time:
        from_time = frappe.utils.nowdate() + " 09:00:00"
    row = {"task": task, "project": project, "from_time": str(from_time),
           "hours": hours, "description": description}
    at = _default_activity_type()
    if at:
        row["activity_type"] = at
    ts = frappe.get_doc({"doctype": "Timesheet", "company": company,
                         "employee": _employee_for(user), "time_logs": [row]})
    ts.insert(ignore_permissions=True)  # scope already checked by caller; native audit
    return ts.name


@frappe.whitelist()
def log(task, hours, log_date=None, description=None):
    """Log worktime hours against a Task (one Draft Timesheet, single row)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not task:
        frappe.throw(_("Task is required."))
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to log time on this task."), frappe.PermissionError)
    # G4.3: cannot log new worktime on a terminal task. Reopen first.
    pmperm.assert_task_not_terminal(
        doc, _("Không thể ghi giờ trên nhiệm vụ đã hoàn thành/huỷ. Vui lòng Reopen trước."))

    try:
        hrs = float(hours)
    except Exception:
        hrs = 0
    if hrs <= 0:
        frappe.throw(_("Hours must be greater than 0."))

    day = log_date or frappe.utils.nowdate()
    try:
        frappe.utils.getdate(day)
    except Exception:
        frappe.throw(_("Ngày ghi giờ không hợp lệ."))
    name = _create_timesheet(user, task, doc.get("project"), hrs, description,
                             from_time=day + " 09:00:00")
    return {"timesheet": name, "task": task, "hours": hrs, "date": day}


@frappe.whitelist()
def list(task=None, project=None, user=None, from_date=None, to_date=None):
    """List worktime rows (Timesheet Detail) by task / project / user / range.

    Returns {rows, total_hours}. Requires `task` or `project`, permission-checked.
    """
    pmperm.require_pm_access()
    me = frappe.session.user

    conds = []
    if task:
        if not pmperm.can_view_task(frappe.get_doc("Task", task).as_dict(), me):
            frappe.throw(_("Not permitted."), frappe.PermissionError)
        conds.append(["task", "=", task])
    elif project:
        if not pmperm.can_view_project(project, me):
            frappe.throw(_("Not permitted."), frappe.PermissionError)
        conds.append(["project", "=", project])
    else:
        frappe.throw(_("Provide a task or a project."))

    if user:
        conds.append(["owner", "=", user])
    if from_date:
        conds.append(["from_time", ">=", from_date + " 00:00:00"])
    if to_date:
        conds.append(["from_time", "<=", to_date + " 23:59:59"])

    rows = frappe.get_all(
        "Timesheet Detail", filters=conds,
        fields=["name", "parent", "task", "project", "from_time", "hours",
                "description", "owner"],
        order_by="from_time desc",
    )
    total = 0
    for r in rows:
        total += (r.get("hours") or 0)

    # Rollup: sum hours logged on direct child tasks so a parent task can show
    # the whole cluster's effort (parent's own rows stay in `rows`/`total_hours`).
    subtask_hours = 0
    if task:
        kids = frappe.get_all("Task", filters={"parent_task": task}, pluck="name")
        if kids:
            for kr in frappe.get_all(
                "Timesheet Detail", filters=[["task", "in", kids]], fields=["hours"]
            ):
                subtask_hours += (kr.get("hours") or 0)

    return {"rows": rows, "total_hours": total, "subtask_hours": subtask_hours}


# Timesheet page paging / top lists (hotfix 23).
REPORT_PEOPLE_LEN = 7      # people table rows per page (PO 27/11)
REPORT_TOP_TASKS = 10      # overall "top task theo giờ"
PERSON_TOP_TASKS = 3       # task names shown per person
_REPORT_FIELDS = ["name", "parent", "task", "project", "from_time", "hours", "description", "owner"]


def _report_rows(user=None, project=None, task=None, from_date=None, to_date=None):
    """THE permission + filter rule of the Timesheet page, shared by report and export_xlsx.
    Managers and Management see all (optionally one user); everyone else only their own logs."""
    pmperm.require_pm_access()
    me = frappe.session.user
    conds = []
    if task:
        conds.append(["task", "=", task])
    if project:
        conds.append(["project", "=", project])
    if from_date:
        conds.append(["from_time", ">=", str(from_date)[:10] + " 00:00:00"])
    if to_date:
        conds.append(["from_time", "<=", str(to_date)[:10] + " 23:59:59"])
    if pmperm.can_see_all_pm_data(me):
        if user:
            conds.append(["owner", "=", user])
    else:
        conds.append(["owner", "=", me])  # non-managers: own logs only
    return frappe.get_all("Timesheet Detail", filters=conds, fields=_REPORT_FIELDS,
                          order_by="from_time desc", limit_page_length=0)


def _hrs(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _r2(v):
    return round(v + 0.0, 2)


def _labels(rows):
    """(task -> subject, project -> project_name, user -> full_name), one query each."""
    tasks = sorted({r.get("task") for r in rows if r.get("task")})
    projs = sorted({r.get("project") for r in rows if r.get("project")})
    users = sorted({r.get("owner") for r in rows if r.get("owner")})
    subj, pname, full = {}, {}, {}
    if tasks:
        for t in frappe.get_all("Task", filters={"name": ["in", tasks]}, fields=["name", "subject"],
                                limit_page_length=0):
            subj[t["name"]] = t.get("subject") or t["name"]
    if projs:
        for p in frappe.get_all("Project", filters={"name": ["in", projs]},
                                fields=["name", "project_name"], limit_page_length=0):
            pname[p["name"]] = p.get("project_name") or p["name"]
    if users:
        for u in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"],
                                limit_page_length=0):
            full[u["name"]] = u.get("full_name") or u["name"]
    return subj, pname, full


def _top(hours_by_task, subj, n, extra=None):
    items = sorted(hours_by_task.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    out = []
    for t, h in items:
        row = {"task": t, "subject": subj.get(t) or t, "hours": _r2(h)}
        if extra:
            row.update(extra(t))
        out.append(row)
    return out


@frappe.whitelist()
def report(user=None, project=None, task=None, from_date=None, to_date=None,
           people_start=0, people_len=REPORT_PEOPLE_LEN):
    """Aggregated worktime report for the Timesheet page.

    Filters: user / project / task / date range. Permission: managers and
    Management see all; everyone else sees only their own logs (owner = me).
    Returns rows + total_hours + by_day/by_week/by_month summaries (meaning unchanged).
    Hotfix 23 additions (same filtered rows, nothing new is exposed):
      top_tasks     [{task, subject, project, project_name, hours}]  top REPORT_TOP_TASKS
      by_project    [{project, project_name, hours}]                hours desc ("" = no project)
      people        [{user, full_name, hours, logs, days, top_tasks:[{task, subject, hours}]}]
                    hours desc, paged by people_start / people_len (default 7)
      people_total  number of people before paging
    """
    rows = _report_rows(user, project, task, from_date, to_date)
    try:
        people_start = max(0, int(people_start or 0))
    except (TypeError, ValueError):
        people_start = 0
    try:
        people_len = int(people_len) if people_len not in (None, "") else REPORT_PEOPLE_LEN
    except (TypeError, ValueError):
        people_len = REPORT_PEOPLE_LEN
    if people_len <= 0:
        people_len = REPORT_PEOPLE_LEN

    total = 0
    by_day, by_week, by_month = {}, {}, {}
    by_task, by_proj, per = {}, {}, {}
    for r in rows:
        hrs = r.get("hours") or 0
        total += hrs
        h = _hrs(hrs)
        if r.get("task"):
            by_task[r["task"]] = by_task.get(r["task"], 0) + h
        pk = r.get("project") or ""
        by_proj[pk] = by_proj.get(pk, 0) + h
        if r.get("owner"):
            pp = per.setdefault(r["owner"], {"hours": 0.0, "logs": 0, "days": set(), "tasks": {}})
            pp["hours"] += h
            pp["logs"] += 1
            if r.get("task"):
                pp["tasks"][r["task"]] = pp["tasks"].get(r["task"], 0) + h
        ft = r.get("from_time")
        if not ft:
            continue
        try:
            dobj = frappe.utils.getdate(ft)  # date object (handles datetime / str)
        except Exception:
            continue
        dkey = dobj.isoformat()              # "YYYY-MM-DD" string
        if r.get("owner"):
            per[r["owner"]]["days"].add(dkey)
        by_day[dkey] = by_day.get(dkey, 0) + hrs
        mkey = dkey[:7]                       # slice on ISO string (safe)
        by_month[mkey] = by_month.get(mkey, 0) + hrs
        iso = dobj.isocalendar()
        wkey = "%04d-W%02d" % (iso[0], iso[1])
        by_week[wkey] = by_week.get(wkey, 0) + hrs

    subj, pname, full = _labels(rows)
    task_proj = {}
    for r in rows:
        if r.get("task") and r.get("project"):
            task_proj.setdefault(r["task"], r["project"])
    top_tasks = _top(by_task, subj, REPORT_TOP_TASKS,
                     extra=lambda t: {"project": task_proj.get(t),
                                      "project_name": pname.get(task_proj.get(t)) if task_proj.get(t) else None})
    by_project = [{"project": p or None, "project_name": (pname.get(p) or p) if p else None, "hours": _r2(h)}
                  for p, h in sorted(by_proj.items(), key=lambda kv: (-kv[1], kv[0]))]
    ranked = sorted(per.items(), key=lambda kv: (-kv[1]["hours"], kv[0]))
    people = [{"user": u, "full_name": full.get(u) or u, "hours": _r2(pp["hours"]), "logs": pp["logs"],
               "days": len(pp["days"]), "top_tasks": _top(pp["tasks"], subj, PERSON_TOP_TASKS)}
              for u, pp in ranked[people_start:people_start + people_len]]
    return {"rows": rows, "total_hours": total,
            "by_day": by_day, "by_week": by_week, "by_month": by_month,
            "top_tasks": top_tasks, "by_project": by_project,
            "people": people, "people_total": len(ranked)}


_XLSX_HEADER = ["Ngày", "Người", "Email", "Dự án", "Việc", "Mã việc", "Giờ", "Mô tả"]


@frappe.whitelist()
def export_xlsx(user=None, project=None, task=None, from_date=None, to_date=None):
    """Hotfix 23 "Xuất Excel": the SAME filtered rows as report (same permission rule via
    _report_rows - a non-manager only ever exports their own logs), one line per log, readable
    names instead of codes. Streams an .xlsx (frappe.response binary)."""
    rows = _report_rows(user, project, task, from_date, to_date)
    subj, pname, full = _labels(rows)
    data = [_XLSX_HEADER]
    for r in rows:
        data.append([str(r.get("from_time") or "")[:10], full.get(r.get("owner")) or r.get("owner") or "",
                     r.get("owner") or "", pname.get(r.get("project")) or r.get("project") or "",
                     subj.get(r.get("task")) or r.get("task") or "", r.get("task") or "",
                     _r2(_hrs(r.get("hours"))), r.get("description") or ""])
    from frappe.utils.xlsxutils import make_xlsx
    xlsx = make_xlsx(data, "Timesheet")
    span = "_".join(frappe.utils.getdate(x).isoformat() for x in (from_date, to_date) if x)   # QC: never echo raw input into the filename
    frappe.response["filename"] = "timesheet{0}.xlsx".format(("_" + span) if span else "")
    frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "binary"
