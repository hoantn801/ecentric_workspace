"""PM v2 - G4.1 hotfix (permanent): no-len Workflow condition for 'Hoàn thành'.

Frappe Workflow `safe_eval` does NOT expose len() (nor all()/any()). The p006
condition used len(...), crashing `tasks.get -> get_transitions` with
`NameError: name 'len' is not defined` -> the task modal hung on the spinner.
(Already hotfixed manually in Desk; this patch makes it permanent + reproducible.)

Idempotently rewrites every PM Task Workflow transition with
action == "Hoàn thành" and next_state == "Done" to a list-TRUTHINESS condition
(a non-empty list is truthy; `not []` is True) -- same logic, no len/all/any.
ADDITIVE corrective only: does NOT add/remove/recreate transitions or change
workflow structure. Saves the Workflow normally. Safe to run multiple times.

(p006 carries the same condition for fresh installs.)
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
ACTION = "Hoàn thành"
NEXT_STATE = "Done"
CONDITION = (
    "doc.pm_checklist "
    "and not [d for d in doc.pm_checklist if d.is_required and not d.is_done] "
    "and ([d for d in doc.pm_checklist if d.is_required] "
    "or not [d for d in doc.pm_checklist if not d.is_done])"
)


def execute():
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        return
    wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
    changed = False
    for t in wf.transitions:
        if t.action == ACTION and t.next_state == NEXT_STATE and (t.condition or "") != CONDITION:
            t.condition = CONDITION
            changed = True
    if changed:
        wf.save(ignore_permissions=True)
        frappe.clear_cache(doctype="Task")
