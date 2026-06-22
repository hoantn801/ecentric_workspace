"""PM v2 - G4.2: gate the existing 'Mark Done' (Review -> Done) transition by checklist.

For tasks WITH a checklist, Done must not be reachable via 'Mark Done' until the
checklist completion rule is satisfied. For tasks WITHOUT a checklist, 'Mark Done'
stays unchanged.

Idempotently sets a safe_eval condition (NO len()/all()/any() -> list truthiness) on
the existing Review --Mark Done--> Done transition(s). ADDITIVE: does NOT remove
'Mark Done', does NOT change task statuses or workflow structure. Safe to run many times.

(The separate 'Hoàn thành' transition from p006/p007 also reaches Done when the
checklist is complete; both are legal one-step paths for a checklist-complete task.)
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
ACTION = "Mark Done"
STATE = "Review"
NEXT_STATE = "Done"
# no checklist  OR  checklist-complete (required-driven; list truthiness, no len/all/any)
CONDITION = (
    "(not doc.pm_checklist) or ("
    "doc.pm_checklist "
    "and not [d for d in doc.pm_checklist if d.is_required and not d.is_done] "
    "and ([d for d in doc.pm_checklist if d.is_required] "
    "or not [d for d in doc.pm_checklist if not d.is_done]))"
)


def execute():
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        return
    wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
    changed = False
    for t in wf.transitions:
        if (t.action == ACTION and t.state == STATE and t.next_state == NEXT_STATE
                and (t.condition or "") != CONDITION):
            t.condition = CONDITION
            changed = True
    if changed:
        wf.save(ignore_permissions=True)
        frappe.clear_cache(doctype="Task")
