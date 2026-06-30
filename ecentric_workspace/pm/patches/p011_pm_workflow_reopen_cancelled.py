"""PM v2 - Batch G4.11: 'Mở lại' transition (Cancelled -> To Do).

Idempotent + metadata-preserving (ADDS one edge; never rebuilds the table, so existing
conditions/allow_self_approval on other rows are untouched). The new transition lets a
LEADER reopen a cancelled task:

  Cancelled --[Mở lại]--> To Do   allowed: System Manager + PM Manager

PM Member is intentionally NOT allowed (administrative). Cancelled stays terminal/immutable
(is_task_terminal unchanged) until 'Mở lại' is applied; full audit is retained via apply_workflow.
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
ACTION = "Mở lại"
FROM_STATE = "Cancelled"
TO_STATE = "To Do"
ROLES = ["System Manager", "PM Manager"]


def execute():
    if not frappe.db.exists("Workflow", WORKFLOW_NAME):
        return
    if not frappe.db.exists("Workflow Action Master", ACTION):
        frappe.get_doc({"doctype": "Workflow Action Master",
                        "workflow_action_name": ACTION}).insert(ignore_permissions=True)
    wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
    have = {(t.state, t.action, t.next_state, t.allowed) for t in wf.transitions}
    added = 0
    for role in ROLES:
        if (FROM_STATE, ACTION, TO_STATE, role) in have:
            continue
        wf.append("transitions", {
            "state": FROM_STATE, "action": ACTION, "next_state": TO_STATE,
            "allowed": role, "allow_self_approval": 1,
        })
        added += 1
    if added:
        wf.save(ignore_permissions=True)
        frappe.clear_cache(doctype="Task")
