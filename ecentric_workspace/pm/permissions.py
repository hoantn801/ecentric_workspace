"""PM v2 - backend permission baseline (PM1-T03).

Row-level visibility for Project and Task, enforced SERVER-SIDE via
permission_query_conditions. These functions only take effect once registered in
hooks.py (activation step) and deployed -- this file alone changes nothing.

Access model:
  1. Administrator / System Manager -> all (no restriction).
  2. PM Manager -> ALL PM Project/Task (this phase: PM_MANAGER_SEES_ALL = True).
     The department/manager-scope code is retained but DORMANT; set the toggle
     back to False to re-enable scoped visibility in a later phase.
  3. PM Member -> projects/tasks they own, are a member of, or are assigned.
  4. Assignee -> tasks assigned to them (_assign).
  5. Users with NO PM role -> UNCHANGED/legacy (return "" = no extra restriction)
     so other modules that read Project/Task (e.g. the GBS Project dropdown) are
     NOT affected. This avoids cross-module regression.

No hardcoded users/emails: identity comes from frappe.session.user /
frappe.get_roles only. Single-record reads are additionally checked in the
service layer (PM1-T05..T08) via frappe.has_permission (defense in depth).
"""

import frappe

# Toggle: if True, PM Manager sees ALL PM data instead of department/manager scope.
# Phase 1 decision (OQ-T03a): PM Manager sees ALL PM data.
PM_MANAGER_SEES_ALL = True


def _is_unrestricted(user):
    if user == "Administrator":
        return True
    return "System Manager" in frappe.get_roles(user)


def _has_pm_role(user):
    roles = frappe.get_roles(user)
    return ("PM Manager" in roles) or ("PM Member" in roles)


def _get_user_departments(user):
    """Best-effort: a user's department(s) via their Employee record.

    Returns [] if it cannot be resolved -> manager scope simply omits the
    department clause (fails safe: never grants more than intended).
    """
    depts = set()
    emp = frappe.db.get_value(
        "Employee", {"user_id": user}, ["name", "department"], as_dict=True
    )
    if emp:
        if emp.get("department"):
            depts.add(emp["department"])
        try:
            rows = frappe.get_all(
                "Employee Department Membership",
                filters={"parent": emp["name"]},
                fields=["department"],
            )
            for r in rows:
                if r.get("department"):
                    depts.add(r["department"])
        except Exception:
            # child doctype/fieldname not as expected -> base department only
            pass
    return list(depts)


def _project_visibility_sql(user, alias):
    """WHERE fragment for a Project table referenced as `alias`.

    `alias` is e.g. "`tabProject`" (main query) or "p" (correlated subquery).
    """
    u = frappe.db.escape(user)
    parts = [
        "{a}.owner = {u}".format(a=alias, u=u),
        "{a}.ec_manager = {u}".format(a=alias, u=u),
        "exists (select 1 from `tabProject User` pu "
        "where pu.parent = {a}.name and pu.user = {u})".format(a=alias, u=u),
    ]
    if "PM Manager" in frappe.get_roles(user) and not PM_MANAGER_SEES_ALL:
        depts = _get_user_departments(user)
        if depts:
            dept_in = ", ".join(frappe.db.escape(d) for d in depts)
            parts.append("{a}.ec_department in ({d})".format(a=alias, d=dept_in))
    return "(" + " or ".join(parts) + ")"


def get_permission_query_conditions_for_project(user=None):
    user = user or frappe.session.user
    if _is_unrestricted(user):
        return ""
    if not _has_pm_role(user):
        return ""  # non-PM users unchanged (no cross-module regression)
    if "PM Manager" in frappe.get_roles(user) and PM_MANAGER_SEES_ALL:
        return ""
    return _project_visibility_sql(user, "`tabProject`")


def get_permission_query_conditions_for_task(user=None):
    user = user or frappe.session.user
    if _is_unrestricted(user):
        return ""
    if not _has_pm_role(user):
        return ""
    roles = frappe.get_roles(user)
    if "PM Manager" in roles and PM_MANAGER_SEES_ALL:
        return ""
    u = frappe.db.escape(user)
    like = frappe.db.escape("%" + user + "%")
    proj_sql = _project_visibility_sql(user, "p")
    parts = [
        "`tabTask`.owner = {u}".format(u=u),
        "`tabTask`._assign like {like}".format(like=like),
        "`tabTask`.project in "
        "(select p.name from `tabProject` p where {proj})".format(proj=proj_sql),
    ]
    return "(" + " or ".join(parts) + ")"
