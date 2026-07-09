"""p016 - Adoption-phase PM access: grant the PM Member role to every enabled System User.

Ordering: runs AFTER p015 (PM Member delete lockdown) so at no point during migrate does a
newly-granted user hold delete on the PM sub-objects. Keep this after p015 in patches.txt.

Why: for adoption, any enabled staff member should be able to open /pm and create Projects/Tasks.
PM access (permissions.has_pm_module_access) and Project/Task 'create' DocPerm both key off the PM
roles; PM Member already carries read/write/create on Project + Task (p001) and NO delete/admin.
Granting PM Member to all enabled users is the clean, role-based way to open create-access without
touching DocPerm, schema, or the delete/admin gates (which stay PM Manager / System Manager only).

Method: governed frappe role API only (`User.add_roles`) -> validates + audits. NO raw SQL, NO
ignore_permissions, NO direct child-table writes. Idempotent (skips users who already have the role;
re-running is a no-op). Administrator/Guest and non-System users are excluded.

Scope note: this one-time patch covers users that exist at migrate time. Users created LATER are
NOT auto-covered -- assign PM Member during onboarding (or add it to the new-user role defaults).
"""

import frappe


def execute():
    if not frappe.db.exists("Role", "PM Member"):
        frappe.log_error("p016: Role 'PM Member' not found; skipping.", "p016 PM Member grant")
        return

    users = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User",
                 "name": ["not in", ["Administrator", "Guest"]]},
        pluck="name",
    )
    granted = 0
    for name in users:
        try:
            if "PM Member" in set(frappe.get_roles(name)):
                continue  # already has it (directly or effectively) -> idempotent no-op
            doc = frappe.get_doc("User", name)
            doc.add_roles("PM Member")  # governed: appends role + saves; validates + audits
            granted += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p016 grant PM Member: %s" % name)
    print("[p016] PM Member granted to %d of %d enabled System Users" % (granted, len(users)))
