"""PM v2 - Batch G4.10: transition-aware PM Task Workflow roles (metadata-preserving).

Idempotent. Adjusts ONLY the `allowed` role coverage of the existing PM Task Workflow
transitions; every other field of each transition row (condition, allow_self_approval, email
template, ordering, ...) is preserved verbatim. This matters because the checklist-completion
gate lives in the `condition` of the `Mark Done` / `Hoàn thành` -> Done edges — a naive rebuild
would silently drop it.

Role policy:
  * operational (non-Cancel) transitions -> System Manager + PM Manager + PM Member
  * Cancel transitions                   -> System Manager + PM Manager  (PM Member REMOVED)

Why System Manager: PM leaders (can_see_all_pm_data) include System-Manager users who had no
workflow role and got zero transitions. Why PM Member off Cancel: PM Member has Task write
DocPerm + no query condition, so removing them from Cancel at the workflow blocks generic
apply_workflow Cancel. Assigned-only for PM Member is enforced by the Task before_save guard
(ecentric_workspace.pm.api.tasks.pm_task_transition_guard). Only PM workflow transition rows
change; no DocPerm change, no new roles, no change to which edges exist.
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
CANCEL_ACTION = "Cancel"
OPERATIONAL_ROLES = ["System Manager", "PM Manager", "PM Member"]
CANCEL_ROLES = ["System Manager", "PM Manager"]

# child-row meta + the role we re-assign per row; everything else is preserved.
_DROP = {"name", "parent", "parentfield", "parenttype", "idx", "creation", "modified",
         "owner", "modified_by", "docstatus", "allowed"}


def execute():
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        return
    wf = frappe.get_doc("Workflow", WORKFLOW_NAME)

    # 1) capture each distinct edge's full field set (sans meta/allowed), first occurrence wins,
    #    preserving original ordering.
    templates, order = {}, []
    for t in wf.transitions:
        key = (t.state, t.action, t.next_state)
        if key in templates:
            continue
        templates[key] = {k: v for k, v in t.as_dict().items()
                          if k not in _DROP and not k.startswith("__")}
        order.append(key)

    # 2) rebuild with the role policy, preserving condition + all other fields. Dedupe by
    #    (state, action, next_state, allowed, condition).
    new_rows, seen = [], set()
    for key in order:
        state, action, next_state = key
        base = templates[key]
        roles = CANCEL_ROLES if action == CANCEL_ACTION else OPERATIONAL_ROLES
        for role in roles:
            ded = (state, action, next_state, role, base.get("condition"))
            if ded in seen:
                continue
            seen.add(ded)
            row = dict(base)
            row["allowed"] = role
            new_rows.append(row)

    wf.set("transitions", [])
    for row in new_rows:
        wf.append("transitions", row)
    wf.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Task")
