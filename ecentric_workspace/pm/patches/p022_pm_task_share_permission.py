"""p022 - grant `share` on Task to the PM roles so assigning a task works.

WHY. `pm.api.tasks.create()` inserts the Task and then calls Frappe's native
`assign_to.add()`. Assignment does not only create a ToDo: Frappe also SHARES the
document with each assignee, and sharing is a separate permission. The baseline
matrix in p001 grants read/write/create (+delete/report/export for PM Manager) but
never `share`, so anyone who is not a System Manager hit:

    No permission to share Task TASK-2026-00375
    Not permitted

...the moment they created a task with an assignee. System Managers were unaffected
(that role keeps `share` from ERPNext's standard perms), which is why this went
unnoticed until a PM-role user tried it. The throw happens AFTER the insert, so the
whole request rolls back -- no orphan Task, but the person loses everything they typed.

WHAT. Add `share = 1` for PM Manager and PM Member on Task, at permlevel 0. Nothing
else in the matrix is touched.

SCOPE. Task only -- Project is not assigned through the PM UI, so it does not need it.
Row-level visibility is unchanged: `ecentric_workspace.pm.permissions.*` still decides
which tasks a user can see, and the service layer validates every assignee before
calling assign_to (see tasks.py `_asg_emails`). `share` only lets these roles do what
assigning already implies.

Idempotent: update_permission_property just re-sets the value on re-run.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

ROLES = ("PM Manager", "PM Member")


def execute():
    for role in ROLES:
        # add_permission no-ops when the permlevel-0 rule already exists (p001 created it)
        add_permission("Task", role, 0)
        update_permission_property("Task", role, 0, "share", 1, validate=False)
    frappe.clear_cache()
