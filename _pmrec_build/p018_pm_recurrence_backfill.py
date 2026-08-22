"""PM v2 - Redesign 2026-08-04 (p018): backfill self-contained template + delete source tasks.

Idempotent. Runs AFTER p017 (schema exists). For every rule that still has a `source_task` and
NO `template_subject` yet:

  1. Snapshot the source Task onto the rule (subject/desc/priority/assignees/time/duration),
     its checklist (source Task's own pm_checklist, else the linked checklist_template's items),
     its direct sub-tasks (one level), and its labels -> rule child tables + JSON fields.
  2. Delete the source Task (decision: 'xoá task gốc'). Its direct template children are deleted
     first; the rule's source_task Link is cleared to release link integrity, then the Task is
     hard-deleted. FALLBACK: if any delete is blocked, the record is orphaned/cancelled + logged
     so the migration always completes (never half-fails).

Already-generated occurrence Tasks are NEVER touched. Safe to run multiple times (skips rules that
already carry a template_subject).
"""

import json

import frappe
from frappe.utils import getdate


def _labels_of(task):
    return [a["label"] for a in frappe.get_all(
        "PM Task Label Assignment", filters={"task": task}, fields=["label"],
        limit_page_length=0, ignore_permissions=True) if a.get("label")]


def _delete_task(name):
    """Hard-delete a Task; return True on success, False if blocked (caller handles fallback)."""
    try:
        frappe.delete_doc("Task", name, force=1, ignore_permissions=True,
                          delete_permanently=True)
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p018 delete task blocked: " + str(name))
        return False


def _backfill_one(rule_name):
    r = frappe.get_doc("PM Recurrence", rule_name)
    src_name = r.get("source_task")
    if not src_name or not frappe.db.exists("Task", src_name):
        # nothing to migrate from; just clear the dangling link so the rule is clean
        if src_name:
            frappe.db.set_value("PM Recurrence", rule_name, "source_task", None)
        return "empty"
    src = frappe.get_doc("Task", src_name)

    # --- 1) snapshot scalar template fields ---
    r.template_subject = src.get("subject") or src_name
    r.template_description = src.get("description")
    r.template_priority = src.get("priority")
    try:
        r.template_assignees = json.dumps([u for u in (frappe.parse_json(src.get("_assign") or "[]") or []) if u])
    except Exception:
        r.template_assignees = "[]"
    r.template_start_time = src.get("pm_start_time")
    r.template_end_time = src.get("pm_end_time")
    dur = 0
    if src.get("exp_start_date") and src.get("exp_end_date"):
        dur = max(0, (getdate(src.exp_end_date) - getdate(src.exp_start_date)).days)
    r.template_duration_days = dur

    # --- 2) checklist: source Task's own items, else the linked checklist_template ---
    r.set("pm_checklist_items", [])
    citems = src.get("pm_checklist") or []
    if not citems and r.get("checklist_template") and \
            frappe.db.exists("PM Checklist Template", r.get("checklist_template")):
        tmpl = frappe.get_doc("PM Checklist Template", r.get("checklist_template"))
        for it in sorted(tmpl.get("items") or [], key=lambda x: (x.idx or 0)):
            r.append("pm_checklist_items", {
                "item_label": it.item_label, "is_required": 1 if it.is_required else 0})
    else:
        for it in citems:
            r.append("pm_checklist_items", {
                "item_label": it.get("item_label"),
                "is_required": 1 if it.get("is_required") else 0})

    # --- 3) direct sub-tasks (one level) ---
    r.set("pm_subtasks", [])
    kids = frappe.get_all("Task", filters={"parent_task": src_name},
                          fields=["name", "subject", "description", "priority", "_assign"],
                          order_by="creation asc", limit_page_length=0, ignore_permissions=True)
    for k in kids:
        try:
            asg = json.dumps([u for u in (frappe.parse_json(k.get("_assign") or "[]") or []) if u])
        except Exception:
            asg = "[]"
        r.append("pm_subtasks", {
            "subject": k.get("subject") or "(no subject)",
            "description": k.get("description"),
            "priority": k.get("priority"), "assignees": asg})

    # --- 4) labels ---
    r.template_labels = json.dumps(_labels_of(src_name))

    r.save(ignore_permissions=True)

    # --- 5) delete the source task (and its direct template children) ---
    # release link integrity: clear the rule's source_task pointer + label assignments first
    frappe.db.set_value("PM Recurrence", rule_name, "source_task", None)
    for a in frappe.get_all("PM Task Label Assignment", filters={"task": src_name},
                            fields=["name"], limit_page_length=0, ignore_permissions=True):
        try:
            frappe.delete_doc("PM Task Label Assignment", a["name"], force=1,
                              ignore_permissions=True)
        except Exception:
            pass
    # children first (they were snapshotted into pm_subtasks)
    for k in kids:
        if not _delete_task(k["name"]):
            # fallback: orphan + cancel so it never blocks and is visibly retired
            try:
                frappe.db.set_value("Task", k["name"], {"parent_task": None,
                                                        "workflow_state": "Cancelled"})
            except Exception:
                pass
    # finally the source task itself
    if _delete_task(src_name):
        return "deleted"
    try:
        frappe.db.set_value("Task", src_name, "workflow_state", "Cancelled")
    except Exception:
        pass
    frappe.log_error("Rule {0}: source task {1} could not be deleted, cancelled instead.".format(
        rule_name, src_name), "p018 fallback hide")
    return "hidden"


def execute():
    if not frappe.db.exists("DocType", "PM Recurrence Checklist Item"):
        return  # p017 must run first
    rules = frappe.get_all("PM Recurrence",
                           filters={"source_task": ["is", "set"]},
                           fields=["name", "template_subject"], limit_page_length=0)
    migrated = deleted = hidden = 0
    for row in rules:
        if row.get("template_subject"):
            continue  # already migrated (idempotent)
        try:
            res = _backfill_one(row["name"])
            migrated += 1
            if res == "deleted":
                deleted += 1
            elif res == "hidden":
                hidden += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "p018 backfill failed: " + str(row["name"]))
    frappe.logger().info("p018 PM Recurrence backfill: migrated=%s deleted=%s hidden=%s"
                         % (migrated, deleted, hidden))
