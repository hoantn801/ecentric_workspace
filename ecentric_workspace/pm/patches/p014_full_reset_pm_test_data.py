"""p014 - One-time FULL PM operational-data reset (owner-approved; all PM data confirmed TEST).

Purpose
-------
Wipe every PM *operational* record so the module starts clean for real adoption, while
PRESERVING all application structure and configuration:
  KEEP  - app code, DocType definitions, schema, Workflow defs (PM Task Workflow), roles &
          permissions, User & Department masters, PM Web Page/frontend, scheduler config,
          and ALL non-PM data (Alert Center, approval system, notification/action center defs),
          and any Timesheet that is NOT linked to a PM Task.
  DELETE- native Task/Project records that /pm manages (the whole dataset; /pm is permission-
          scoped, and the owner confirmed every Task/Project shown in /pm is test), every
          PM-owned transactional DocType (PM Assignment Request + event child, PM Recurrence,
          PM Timer, PM Task Label Assignment, PM Task Label, PM Checklist Template + item child),
          Task-linked native ToDo assignments, and the *validated* Draft Timesheets that log a
          reset Task. Task child rows (PM Task Checklist Item), Comments and File attachments are
          removed by Frappe's normal delete cascade.

Transaction / safety
--------------------
* ALL-OR-NOTHING: NO explicit frappe.db.commit() anywhere. The patch runs inside the standard
  Frappe patch/migrate transaction; on success migrate commits once, and on ANY exception (a
  blocker or a safety assertion) migrate rolls back the entire reset. No manual rollback or
  transaction manipulation is performed.
* normal frappe.delete_doc only -> hooks + child cascade. NO raw SQL, NO ignore_permissions,
  NO force delete, NO hook edits, NO schema change, NO faked framework flags.
* The PM audit guard (pm_assignment_request_before_delete) and Task transition guard
  (pm_task_transition_guard) both early-return in install/migrate/patch context -- the app
  authors' sanctioned maintenance path, entered via the real runner (not a faked flag).
* Timesheet deletion is strictly validated (Draft-only, PM-Task-only, no billing/Sales
  Invoice/Salary Slip/financial link); any violation STOPS the whole reset with the exact
  Timesheet + link. Submitted Timesheets are never auto-cancelled.
* Idempotent: every step re-queries live data; a rolled-back or partial state re-runs cleanly.
"""

import frappe

# PM-owned transactional DocTypes that must end at count 0 (verification set).
_PM_OP_DOCTYPES = [
    "Task", "Project", "PM Assignment Request", "PM Recurrence", "PM Timer",
    "PM Task Label Assignment", "PM Task Label", "PM Checklist Template",
]


def _delete_all(doctype, log, failed):
    """Delete every record of ``doctype`` one by one via governed delete_doc. Records that cannot
    be removed (a link still held) are recorded in ``failed`` and surfaced by the final assertion."""
    for name in frappe.get_all(doctype, pluck="name"):
        try:
            frappe.delete_doc(doctype, name)  # hooks + cascade; no force, no ignore_permissions
            log.append("%s %s" % (doctype, name))
        except Exception:
            failed.append("%s %s" % (doctype, name))
            frappe.log_error(frappe.get_traceback(), "p014 PM reset: delete %s %s" % (doctype, name))


def _referenced(child_doctype, field, value):
    """True if any ``child_doctype`` row references ``value`` via ``field``; False if that
    DocType is not installed (defensive -- never raises)."""
    try:
        return bool(frappe.db.exists(child_doctype, {field: value}))
    except Exception:
        return False


def execute():
    # Only run inside the real migrate/patch runner (the guards + all-or-nothing rely on it).
    if not (frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install):
        frappe.throw("p014 PM reset must run in the standard patch/migrate runner "
                     "(frappe.flags.in_patch not set). Aborting to avoid an out-of-context run.")

    log, failed = [], []

    # 1) PM Timers (frees the Task 'running/paused timer' link).
    _delete_all("PM Timer", log, failed)

    # 2) PM Assignment Requests incl. Accepted/Rejected/Cancelled + event child rows
    #    (on_trash guard permits deletion in patch context).
    _delete_all("PM Assignment Request", log, failed)

    # 3) PM Recurrence rules (frees source_task / last_task links).
    _delete_all("PM Recurrence", log, failed)

    # 4) PM Task Label Assignments (frees task<->label links so labels become unused).
    _delete_all("PM Task Label Assignment", log, failed)

    # 5) Native ToDo assignments that reference a Task.
    for name in frappe.get_all("ToDo", filters={"reference_type": "Task"}, pluck="name"):
        try:
            frappe.delete_doc("ToDo", name)
            log.append("ToDo %s" % name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p014 PM reset: delete ToDo %s" % name)

    # 6) Clear ERPNext task dependencies (depends_on child rows) that otherwise block delete_doc.
    #    Transition guard no-ops in patch context, so this save is safe.
    for name in frappe.get_all("Task", pluck="name"):
        doc = frappe.get_doc("Task", name)
        if doc.get("depends_on"):
            doc.set("depends_on", [])
            doc.save()

    # The reset Task set = the whole /pm Task dataset (owner-confirmed test). Captured BEFORE any
    # Task is deleted so Timesheet validation can be scoped to exactly these Tasks.
    reset_tasks = set(frappe.get_all("Task", pluck="name"))

    # 6b) STRICT-SAFE Timesheet cleanup (before Task deletion). A Timesheet Detail.task link raises
    #     LinkExistsError on Task deletion. Select ONLY Timesheets that have a detail row whose task
    #     is in the reset set; validate each is a plain Draft PM timesheet with no financial linkage;
    #     abort the whole reset on any violation. Timesheets with no PM-Task link are never selected.
    ts_names = set()
    if reset_tasks:
        for row in frappe.get_all("Timesheet Detail",
                                  filters={"task": ["in", list(reset_tasks)]},
                                  fields=["parent", "task"]):
            if row.get("task") and row.get("parent"):
                ts_names.add(row["parent"])
    for name in sorted(ts_names):
        if not frappe.db.exists("Timesheet", name):
            continue
        doc = frappe.get_doc("Timesheet", name)
        # -- submission / financial safety assertions (stop-the-reset on any violation) --
        if doc.docstatus != 0:
            frappe.throw("p014: refuse to delete non-Draft Timesheet %s (docstatus=%s)."
                         % (name, doc.docstatus))
        for tl in (doc.get("time_logs") or []):
            if tl.get("task") and tl.get("task") not in reset_tasks:
                frappe.throw("p014: Timesheet %s logs non-reset Task %s (not PM-exclusive); abort."
                             % (name, tl.get("task")))
            if tl.get("sales_invoice"):
                frappe.throw("p014: Timesheet %s row is linked to Sales Invoice %s; abort."
                             % (name, tl.get("sales_invoice")))
        if doc.get("salary_slip"):
            frappe.throw("p014: Timesheet %s is linked to Salary Slip %s; abort."
                         % (name, doc.get("salary_slip")))
        if doc.get("per_billed") or doc.get("total_billed_hours") or doc.get("total_billed_amount"):
            frappe.throw("p014: Timesheet %s is billed; abort." % name)
        if _referenced("Sales Invoice Timesheet", "time_sheet", name):
            frappe.throw("p014: Timesheet %s is referenced by a Sales Invoice; abort." % name)
        if _referenced("Salary Slip Timesheet", "time_sheet", name):
            frappe.throw("p014: Timesheet %s is referenced by a Salary Slip; abort." % name)
        # validated: plain Draft, PM-Task-only, unbilled, no financial link -> normal delete
        frappe.delete_doc("Timesheet", name)
        log.append("Timesheet %s" % name)

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

    # 8) Projects.
    _delete_all("Project", log, failed)

    # 9) PM Labels (now unused -> label on_trash guard allows deletion).
    _delete_all("PM Task Label", log, failed)

    # 10) PM Checklist Templates (+ PM Checklist Template Item child rows cascade).
    _delete_all("PM Checklist Template", log, failed)

    # ---- post-reset verification (fail loud; migrate rolls back all on throw) -------------
    counts = {dt: frappe.db.count(dt) for dt in _PM_OP_DOCTYPES}
    tsd_with_task = frappe.db.count("Timesheet Detail", {"task": ["is", "set"]})
    ts_still_selected = set()
    for row in frappe.get_all("Timesheet Detail", filters={"task": ["is", "set"]},
                              fields=["parent"]):
        if row.get("parent"):
            ts_still_selected.add(row["parent"])
    counts["Timesheet Detail (task set)"] = tsd_with_task
    counts["Timesheets linked to a Task"] = len(ts_still_selected)

    print("[p014 PM reset] deleted %d records; remaining: %s" % (len(log), counts))
    if failed:
        print("[p014 PM reset] could-not-delete (see Error Log): %s" % failed)
    frappe.logger("pm_reset").info(
        {"patch": "p014_full_reset_pm_test_data", "deleted": len(log),
         "deleted_ids": log, "failed": failed, "remaining": counts})

    non_zero = {k: v for k, v in counts.items() if v}
    if non_zero:
        frappe.throw("p014 PM reset incomplete; still present: %s. Failed items: %s"
                     % (non_zero, failed))
