"""PM v2 - G4: governed 'Hoan thanh' (checklist-complete) transition to Done.

Idempotent + ADDITIVE: appends transitions to the EXISTING PM Task Workflow WITHOUT
removing/altering existing ones. A safe_eval `condition` (NO all()/any() -> uses the
len([...]) pattern) scopes the action to tasks whose REQUIRED checklist items are all
done; tasks WITHOUT a checklist make the condition False, so they never see it and
their workflow is unchanged. Done is otherwise reachable only via Review -> this lets a
daily routine/checklist task complete in one governed, audited step.

NOTE: do NOT re-run p002 after this patch -- p002 rebuilds the transitions list from
scratch and would drop these. Patches run once (tracked in the `patches` table).

Inert until listed in patches.txt + migrate. Safe to run multiple times.
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
ACTION = "Hoàn thành"
FROM_STATES = ["Backlog", "To Do", "In Progress", "Review"]
ROLES = ["PM Manager", "PM Member"]

# safe_eval-compatible (no all()/any()): checklist exists AND no REQUIRED item left
# undone AND (there is >=1 required item, OR nothing at all is left undone).
CONDITION = (
    "len(doc.pm_checklist or []) > 0 "
    "and len([d for d in doc.pm_checklist if d.is_required and not d.is_done]) == 0 "
    "and (len([d for d in doc.pm_checklist if d.is_required]) > 0 "
    "or len([d for d in doc.pm_checklist if not d.is_done]) == 0)"
)


def execute():
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        return  # base workflow (p002) must exist first
    if not frappe.db.exists("Workflow Action Master", ACTION):
        frappe.get_doc({"doctype": "Workflow Action Master",
                        "workflow_action_name": ACTION}).insert(ignore_permissions=True)

    wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
    existing = {(t.state, t.action, t.allowed) for t in wf.transitions}
    added = False
    for from_state in FROM_STATES:
        for role in ROLES:
            if (from_state, ACTION, role) in existing:
                continue
            wf.append("transitions", {
                "state": from_state, "action": ACTION, "next_state": "Done",
                "allowed": role, "allow_self_approval": 1, "condition": CONDITION,
            })
            added = True
    if added:
        wf.save(ignore_permissions=True)
        frappe.clear_cache(doctype="Task")
