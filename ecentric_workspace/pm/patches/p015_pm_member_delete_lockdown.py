"""p015 - Adoption-phase safety: remove PM Member DELETE on PM operational sub-objects.

Context: p016 grants the PM Member role to every enabled System User. Before that grant,
tighten PM Member so the wider audience does NOT inherit delete on shared/operational PM
records. Adoption policy = open CREATE for Project/Task, keep DELETE / admin / config gated
to PM Manager / System Manager.

DocTypes reconciled here (live site already created them via p003/p004/p005 with the old
delete=1; those source patches early-return if the DocType exists, so this patch is what
actually flips the live permission). The source patches p003/p004/p005 were also updated to
delete=0 so a FRESH install is correct without this reconcile.

  - PM Timer              -> stop-timer deletes the transient row via the service layer
                             (timer.stop -> delete_doc ignore_permissions=True, force=True),
                             so members never need generic delete DocPerm. Removing it does
                             NOT break the stop-timer UX.
  - PM Recurrence         -> rules are soft-cancelled via the service (recurrence.cancel ->
                             status=Cancelled), never hard-deleted by members.
  - PM Checklist Template -> shared/admin-ish config; members edit via the service, never
                             delete templates.

After this patch, PM Member delete=0 on all three; PM Manager / System Manager keep delete=1.
Project / Task delete were never granted to PM Member (unchanged here).

Method: governed frappe API only -- load the DocType, flip the PM Member DocPerm row's delete
flag, save (rebuilds perms + audits). NO raw SQL, NO ignore_permissions bypass of the change,
NO schema change. Idempotent: if PM Member already has delete=0 (or has no row) the DocType is
left untouched and not re-saved.
"""

import frappe

_TARGET_DOCTYPES = ["PM Timer", "PM Recurrence", "PM Checklist Template"]
_ROLE = "PM Member"


def execute():
    for dt in _TARGET_DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            # sub-object not created yet on this site -> its source patch (p003/p004/p005,
            # now delete=0) will create it correctly. Nothing to reconcile.
            continue

        doc = frappe.get_doc("DocType", dt)
        changed = False
        for perm in doc.permissions:
            if perm.role == _ROLE and perm.delete:
                perm.delete = 0
                changed = True

        if changed:
            doc.save()  # governed: on_update rebuilds custom perms + writes audit trail
            print("[p015] %s: PM Member delete removed (now Manager/System only)" % dt)
        else:
            print("[p015] %s: PM Member delete already 0 (no change)" % dt)
