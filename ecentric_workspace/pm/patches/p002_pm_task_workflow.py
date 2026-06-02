"""PM1-T07 - PM Task Workflow (governed status transitions, auditable).

Idempotent. Creates/refreshes a Frappe Workflow on Task using a DEDICATED
`workflow_state` field (NOT native Task.status, which ERPNext manages itself).

States: Backlog -> To Do -> In Progress -> Blocked -> Review -> Done / Cancelled.
Transitions allowed for roles PM Manager + PM Member (self-approval allowed).

Inert until listed in patches.txt + migrate. Once active, new Tasks default to
Backlog and status changes must go through apply_workflow (governed + audited).
"""

import frappe

WORKFLOW_NAME = "PM Task Workflow"
STATE_FIELD = "workflow_state"
ROLES = ["PM Manager", "PM Member"]

# state -> style
STATES = [
    ("Backlog", ""),
    ("To Do", "Primary"),
    ("In Progress", "Info"),
    ("Blocked", "Danger"),
    ("Review", "Warning"),
    ("Done", "Success"),
    ("Cancelled", "Inverse"),
]

# (from_state, action, next_state)
TRANSITIONS = [
    ("Backlog", "Move to To Do", "To Do"),
    ("To Do", "Start", "In Progress"),
    ("In Progress", "Block", "Blocked"),
    ("Blocked", "Unblock", "In Progress"),
    ("In Progress", "Submit for Review", "Review"),
    ("Review", "Mark Done", "Done"),
    ("Review", "Request Changes", "In Progress"),
    ("Done", "Reopen", "In Progress"),
    ("Backlog", "Cancel", "Cancelled"),
    ("To Do", "Cancel", "Cancelled"),
    ("In Progress", "Cancel", "Cancelled"),
    ("Blocked", "Cancel", "Cancelled"),
    ("Review", "Cancel", "Cancelled"),
]


def _ensure_masters():
    for state, _style in STATES:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": state,
                "style": _style,
            }).insert(ignore_permissions=True)
    actions = sorted({a for _s, a, _n in TRANSITIONS})
    for action in actions:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action,
            }).insert(ignore_permissions=True)


def execute():
    _ensure_masters()

    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
    else:
        wf = frappe.new_doc("Workflow")
        wf.workflow_name = WORKFLOW_NAME

    wf.document_type = "Task"
    wf.is_active = 1
    wf.workflow_state_field = STATE_FIELD
    wf.send_email_alert = 0

    wf.set("states", [])
    for state, style in STATES:
        wf.append("states", {
            "state": state,
            "doc_status": "0",
            "allow_edit": "PM Manager",   # required field; Phase: PM Manager for all states
            "style": style,
        })

    wf.set("transitions", [])
    for from_state, action, next_state in TRANSITIONS:
        for role in ROLES:
            wf.append("transitions", {
                "state": from_state,
                "action": action,
                "next_state": next_state,
                "allowed": role,
                "allow_self_approval": 1,
            })

    wf.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Task")
