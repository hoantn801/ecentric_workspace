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

    try:
        hrs = float(hours)
    except Exception:
        hrs = 0
    if hrs <= 0:
        frappe.throw(_("Hours must be greater than 0."))

    project = doc.get("project")
    company = _company_for(project)
    if not company:
        frappe.throw(_("No Company found. Set Project.company or a default Company."))

    day = log_date or frappe.utils.nowdate()
    row = {
        "task": task,
        "project": project,
        "from_time": day + " 09:00:00",
        "hours": hrs,
        "description": description,
    }
    at = _default_activity_type()
    if at:
        row["activity_type"] = at

    ts = frappe.get_doc({
        "doctype": "Timesheet",
        "company": company,
        "employee": _employee_for(user),
        "time_logs": [row],
    })
    ts.insert(ignore_permissions=True)  # scope already checked; native audit preserved
    return {"timesheet": ts.name, "task": task, "hours": hrs, "date": day}


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
    return {"rows": rows, "total_hours": total}
