# Copyright (c) 2026, eCentric and contributors
"""C4b B4: grant the `EC Sales Admin` Role explicit permissions on the two
native order DocTypes it is required to approve -- `Sales Order` and
`Purchase Order`.

Classification: permission fix (idempotent, additive).

Why this exists
---------------
The EC SO/PO approval flow runs on native Frappe Workflows (`EC SO Approval`,
`EC PO Approval`), single level: Draft -> Pending Sales Admin -> Approved /
Rejected. Approving submits the document, so the approver needs write + submit
on the DocType.

Survey on the live site (2026-08-03) found the Role `EC Sales Admin` has NO
DocPerm row at all on either DocType. The two current holders (dan.ha,
van.bui) can approve only because they *separately* hold the ERPNext roles
`Sales User` and `Purchase User`. That is an accident, not a design: the moment
a third Sales Admin is added without those two extra roles, every approval they
attempt fails with a permission error and nothing in the EC configuration
explains why. This patch makes the Role itself sufficient.

Behaviour contract
------------------
After execute():
  * `EC Sales Admin` has read / write / submit / report / export / print /
    email / share at permlevel 0 on `Sales Order` and `Purchase Order`.
  * `create`, `delete`, `cancel` and `amend` are deliberately NOT granted --
    an approver approves orders, it does not author, void or re-open them.
  * Every permission that existed before is preserved (see side effect).

SIDE EFFECT -- READ THIS BEFORE MIGRATING
-----------------------------------------
`frappe.permissions.add_permission()` calls `setup_custom_perms()`, which on
first use COPIES every standard DocPerm of the DocType into `Custom DocPerm`
(frappe/permissions.py :: copy_perms). From then on Frappe reads permissions
for that DocType from `Custom DocPerm` ONLY and ignores the standard rows
entirely (frappe/model/meta.py).

Nothing is lost right now -- the copy is faithful, and this site currently has
0 Custom DocPerm rows on both DocTypes, so the copy is exact. But it does mean
the two DocTypes stop tracking upstream ERPNext: if a future ERPNext release
changes the stock Sales Order / Purchase Order permission matrix, this site
will keep the 2026-08-03 snapshot. That is the accepted cost of granting a
custom Role on a standard DocType through the supported API.

Rollback
--------
    bench --site <site> execute frappe.permissions.reset_perms --args "['Sales Order']"
    bench --site <site> execute frappe.permissions.reset_perms --args "['Purchase Order']"
`reset_perms` deletes every Custom DocPerm row for the DocType, which restores
the standard ERPNext DocPerms verbatim AND removes the EC Sales Admin grant.
Rolling back therefore re-breaks approval for any Sales Admin who does not also
hold `Sales User` / `Purchase User`.

Idempotent: re-running makes no further change (add_permission is a no-op when
the row exists; update_permission_property rewrites the same values).
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "EC Sales Admin"
DOCTYPES = ("Sales Order", "Purchase Order")

# permlevel 0 rights the approver genuinely needs.
# NOT granted on purpose: create, delete, cancel, amend.
GRANTS = ("read", "write", "submit", "report", "export", "print", "email", "share")


def execute():
    if not frappe.db.exists("Role", ROLE):
        # fail-safe: a bench where the EC roles have not been seeded yet.
        frappe.logger().info("[C4b B4] Role %s missing -- skipped" % ROLE)
        return

    touched = []
    for doctype in DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            continue

        # Creates the Custom DocPerm row (and, on first call for this DocType,
        # snapshots the standard DocPerms into Custom DocPerm -- see docstring).
        add_permission(doctype, ROLE, 0)

        for ptype in GRANTS:
            update_permission_property(doctype, ROLE, 0, ptype, 1, validate=False)

        touched.append(doctype)

    if not touched:
        return

    for doctype in touched:
        frappe.clear_cache(doctype=doctype)

    msg = "[C4b B4] granted %s on %s to Role '%s'" % (
        "/".join(GRANTS), ", ".join(touched), ROLE)
    frappe.logger().info(msg)
    print(msg)
