# Copyright (c) 2026, eCentric and contributors
"""PM access for new staff (02/11/2026).

WHY. /pm is gated by the PM Member / PM Manager role (pm.permissions.require_pm_access).
That role was granted by ONE-SHOT patches (p016, p023), so every person onboarded after the
last run got "You do not have access to the PM module" (02/11: 10 of 13 hires since 09/2026,
incl. vi.le). This module makes the grant part of onboarding instead of a periodic backfill:

  * on_employee_update (doc_event, Employee on_update): an ACTIVE Employee with a linked
    System User gets PM Member if they have neither PM role;
  * backfill_active_employees: the same rule for everyone (used by patch p030).

SAFETY (same audit as p023): PM Member carries permissions only on Project, Task, PM Timer,
PM Recurrence, PM Checklist Template - nothing on payroll / Employee / Salary doctypes.
Never revokes, never touches leavers, disabled users or Website Users. Errors are logged,
never raised (an HR save must not fail because of PM).
"""

import frappe

PM_MEMBER = "PM Member"
PM_ROLES = ("PM Member", "PM Manager")


def grant_pm_member(user):
    """Idempotent. Returns True when the role was added now."""
    if not user or user in ("Administrator", "Guest"):
        return False
    if not frappe.db.exists("Role", PM_MEMBER):
        return False
    info = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not info or not info.get("enabled") or info.get("user_type") != "System User":
        return False
    if set(frappe.get_roles(user)) & set(PM_ROLES):
        return False
    frappe.get_doc("User", user).add_roles(PM_MEMBER)   # governed: validates, saves, audits
    return True


def on_employee_update(doc, method=None):
    """Employee on_update hook: active staff with a user account can open /pm from day one."""
    try:
        if (doc.get("status") or "") != "Active" or not doc.get("user_id"):
            return
        if grant_pm_member(doc.get("user_id")):
            frappe.logger("pm").info("PM Member granted on onboarding: %s" % doc.get("user_id"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM onboarding grant %s" % doc.get("user_id"))


def backfill_active_employees():
    """Grant PM Member to every eligible ACTIVE employee missing a PM role. Returns granted list."""
    granted = []
    for uid in sorted(set(frappe.get_all("Employee", filters={"status": "Active",
                                                              "user_id": ["is", "set"]},
                                         pluck="user_id") or [])):
        try:
            if grant_pm_member(uid):
                granted.append(uid)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM backfill grant %s" % uid)
    return granted
