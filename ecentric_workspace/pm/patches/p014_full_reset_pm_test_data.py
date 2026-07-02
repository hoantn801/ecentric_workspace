"""p014 - One-time FULL PM operational-data reset (owner-approved; all PM data confirmed TEST).

Purpose
-------
Wipe every PM *operational* record so the module starts clean for real adoption, while
PRESERVING all application structure and configuration:
  KEEP  - app code, DocType definitions, schema, Workflow defs (PM Task Workflow), roles &
          permissions, User & Department masters, PM Web Page/frontend, scheduler config,
          and ALL non-PM data (Alert Center, approval system, notification/action center defs).
  DELETE- native Task/Project records that /pm manages (the whole dataset; /pm is permission-
          scoped, not PM-owned-field-scoped, and the owner confirmed every Task/Project shown in
          /pm is test), plus every PM-owned transactional DocType:
            PM Assignment Request (+ event child rows), PM Recurrence, PM Timer,
            PM Task Label Assignment, PM Task Label, PM Checklist Template (+ item child rows),
          and Task-linked native ToDo assignments. Task child rows (PM Task Checklist Item),
          Comments and File attachments are removed by Frappe's normal delete cascade.

Method / safety
---------------
* normal ``frappe.delete_doc`` only -> runs hooks + child-table cascade. NO raw SQL, NO
  ``ignore_permissions``, NO force delete, NO hook edits, NO schema change.
* Runs inside the standard Frappe patch runner where ``frappe.flags.in_patch`` is True. The PM
  audit guard (``pm_assignment_request_before_delete``) and the Task transition guard
  (``pm_task_transition_guard``) both intentionally early-return in install/migrate/patch context
  -- this is the app authors' sanctioned maintenance path, not a bypass.
* Idempotent + safe if partially run: every step re-queries live data; a second run finds nothing
  and exits cleanly.
* Leaf-first Task deletion is computed from the LIVE ``parent_task`` graph (never numeric IDs).
* Logs every deleted id; asserts all PM operational counts are zero at the end (raises otherwise).

Non-PM Task/Project consumers (notification_center, action_center) are read-only aggregators;
they simply reflect the resulting empty state. No non-PM module owns Task/Project on this site.
"""

import frappe

# PM-owned transactional DocTypes that must end at count 0 (verification set).
_PM_OP_DOCTYPES = [
    "Task", "Project", "PM Assignment Request", "PM Recurrence", "PM Timer",
    "PM Task Label Assignment", "PM Task Label", "PM Checklist Template",
]


def _delete_all(doctype, log, failed):
    """Delete every record of ``doctype`` one by one via governed delete_doc. Records that cannot
    be removed (link still held) are recorded in ``failed`` and surfaced by the final assertion."""
    for name in frappe.get_all(doctype, pluck="name"):
        try:
            frappe.delete_doc(doctype, name)  # hooks + cascade; no force, no ignore_permissions
            log.append("%s %s" % (doctype, name))
        except Exception:
            failed.append("%s %s" % (doctype, name))
            frappe.log_error(frappe.get_traceback(), "p014 PM reset: delete %s %s" % (doctype, name))
    frappe.db.commit()


def execute():
    # Only run inside the real migrate/patch runner (the guards rely on this context).
    if not (frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install):
        frappe.throw("p014 PM reset must run in the standard patch/migrate runner "
                     "(frappe.flags.in_patch not set). Aborting to avoid an out-of-context run.")

    log, failed = [], []

    # 1) PM Timers (frees the Task 'running/paused timer' link).
    _delete_all("PM Timer", log, failed)

    # 2) PM Assignment Requests incl. Accepted/Rejected/Cancelled + their event child rows
    #    (guard permits deletion in patch context).
    _delete_all("PM Assignment Request", log, failed)

    # 3) PM Recurrence rules (frees source_task / last_task links).
    _delete_all("PM Recurrence", log, failed)

    # 4) PM Task Label Assignments (frees task<->label links so labels become unused).
    _delete_all("PM Task Label Assignment", log, failed)

    # 5) Native ToDo assignments that reference a Task (removed so no orphan assignment survives).
    for name in frappe.get_all("ToDo", filters={"reference_type": "Task"}, pluck="name"):
        try:
            frappe.delete_doc("ToDo", name)
            log.append("ToDo %s" % name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p014 PM reset: delete ToDo %s" % name)
    frappe.db.commit()

    # 6) Clear ERPNext task dependencies (depends_on child rows) which otherwise block delete_doc
    #    with LinkExistsError. Transition guard no-ops in patch context, so this save is safe.
    for name in frappe.get_all("Task", pluck="name"):
        doc = frappe.get_doc("Task", name)
        if doc.get("depends_on"):
            doc.set("depends_on", [])
            doc.save()
    frappe.db.commit()

    # 7) Delete Tasks LEAF-FIRST from the live parent_task graph (children before parents).
    remaining = set(frappe.get_all("Task", pluck="name"))
    guard = 0
    while remaining and guard < 100000:
        guard += 1
        rows = frappe.get_all("Task", filters={"name": ["in", list(remaining)]},
                              fields=["parent_task"])
        parents = set(r.parent_task for r in rows if r.parent_task)
        leaves = [n for n in remaining if n not in parents and ("Task %s" % n) not in failed]
        if not leaves:
            break  # only undeletable (failed) or a cycle remains -> surfaced by final assertion
        for n in leaves:
            try:
                frappe.delete_doc("Task", n)  # cascades PM Task Checklist Item rows, comments, files
                log.append("Task %s" % n)
            except Exception:
                failed.append("Task %s" % n)
                frappe.log_error(frappe.get_traceback(), "p014 PM reset: delete Task %s" % n)
            remaining.discard(n)
        frappe.db.commit()

    # 8) Projects.
    _delete_all("Project", log, failed)

    # 9) PM Labels (now unused -> label on_trash guard allows deletion).
    _delete_all("PM Task Label", log, failed)

    # 10) PM Checklist Templates (+ PM Checklist Template Item child rows cascade).
    _delete_all("PM Checklist Template", log, failed)

    # ---- report + fail-loud verification -------------------------------------------------
    counts = {dt: frappe.db.count(dt) for dt in _PM_OP_DOCTYPES}
    print("[p014 PM reset] deleted %d records; remaining PM operational counts: %s"
          % (len(log), counts))
    if failed:
        print("[p014 PM reset] could-not-delete (see Error Log): %s" % failed)
    frappe.logger("pm_reset").info(
        {"patch": "p014_full_reset_pm_test_data", "deleted": len(log),
         "deleted_ids": log, "failed": failed, "remaining": counts})

    non_zero = {k: v for k, v in counts.items() if v}
    if non_zero:
        frappe.throw("p014 PM reset incomplete; still present: %s. Failed items: %s"
                     % (non_zero, failed))
