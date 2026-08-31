"""p023 - backfill the PM Member role for active employees who joined after p016.

The E2E permission audit (2026-09-01) found 19 of 68 active employees could not open /pm
at all: `require_pm_access` rejects anyone without PM Member / PM Manager, and p016's
one-shot grant ran before these people were onboarded (p016's own docstring warned new
users are NOT auto-covered). Everything else on their side -- Employee record, Task
DocPerms, workflow roles -- was already in place.

SCOPE, deliberately narrower than p016 (which took every enabled System User): only users
who are the `user_id` of an ACTIVE Employee. Leavers and service accounts are not touched.

SAFETY (audited before granting, 2026-09-01): PM Member touches exactly five doctypes --
Project, Task (custom perms) + PM Timer, PM Recurrence, PM Checklist Template (native).
It carries NO permission on Salary Slip / Salary Structure / Payroll Entry / Employee /
Timesheet / Salary Component at any permlevel, so this grant cannot expose payroll data.
Projects carry no costing data on this site (0/15 with estimated_costing/billable > 0).

Idempotent: add_roles no-ops when the role is already there; re-running is safe. The same
grant should be added to the user-onboarding checklist so this backfill is the last one.
"""

import frappe


def execute():
    if not frappe.db.exists("Role", "PM Member"):
        frappe.log_error("p023: Role 'PM Member' not found; skipping.", "p023 PM Member backfill")
        return

    emp_users = frappe.get_all(
        "Employee", filters={"status": "Active", "user_id": ["is", "set"]},
        pluck="user_id")
    seen, granted, skipped = set(), [], 0
    for uid in emp_users:
        if not uid or uid in seen or uid in ("Administrator", "Guest"):
            continue
        seen.add(uid)
        try:
            info = frappe.db.get_value("User", uid, ["enabled", "user_type"], as_dict=True)
            if not info or not info.enabled or info.user_type != "System User":
                skipped += 1
                continue
            roles = set(frappe.get_roles(uid))
            if "PM Member" in roles or "PM Manager" in roles:
                continue
            doc = frappe.get_doc("User", uid)
            doc.add_roles("PM Member")  # governed: appends + saves; validates + audits
            granted.append(uid)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p023 grant PM Member: %s" % uid)
    print("[p023] PM Member granted to %d users (skipped %d non-eligible): %s"
          % (len(granted), skipped, ", ".join(granted)))
