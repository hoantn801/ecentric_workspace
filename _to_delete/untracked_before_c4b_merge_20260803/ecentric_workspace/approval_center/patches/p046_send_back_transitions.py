# Copyright (c) 2026, eCentric and contributors
"""C4b B7: add the "Request Changes" (gui lai / can sua) transition to the three
native EC approval Workflows -- `MSO Approval`, `EC SO Approval`, `EC PO Approval`.

Classification: workflow configuration (idempotent, additive).

Why this exists
---------------
Until now an approver on MSO / Sales Order / Purchase Order had exactly two
outcomes: Approve, or Reject. Reject is terminal-feeling and wrong for the
common case "the numbers are fine, one field is missing" -- the requester had to
be told out of band, then use `Rejected --Resubmit-->` to get back in. The GBS
SO/PO flow has had a proper Send back step for months; this brings the three
native flows to parity, as agreed 2026-08-03.

What "Cần sửa" is, and is NOT
-----------------------------
It is NOT a workflow state. No `Workflow State` row is created, and
`workflow_state` remains the single source of truth for where a document is.
Send back moves the document to the EXISTING `Draft` state -- the same place a
brand-new document sits -- and separately records WHY, in the Custom Field
`ec_revision_reason` (shipped as a fixture, see hooks.py).

"Cần sửa" is a display label the approval page derives from
(workflow_state == "Draft") AND (ec_revision_reason is non-empty).
`ec_*_before_save` clears `ec_revision_reason` when the document is submitted
again, so the label disappears on its own. Nothing stores a status twice.

Behaviour contract
------------------
After execute(), each of these transitions exists with allow_self_approval = 1
(matching every pre-existing transition on these three workflows -- the real
identity check lives in the `ec_*_before_save` Server Scripts, which run on
every path including Desk and REST, not in the workflow row):

  MSO Approval
    Pending Manager --Request Changes--> Draft   (All)
    Pending Finance --Request Changes--> Draft   (EC Finance, Administrator)
    Pending HOF     --Request Changes--> Draft   (EC HOF,     Administrator)
    Pending CEO     --Request Changes--> Draft   (EC CEO,     Administrator)
  EC SO Approval / EC PO Approval
    Pending Sales Admin --Request Changes--> Draft (EC Sales Admin, Administrator)

The allowed roles mirror, state for state, whoever may already Approve at that
state -- send back grants no one any reach they did not already have.

`Request Changes` already exists as a `Workflow Action Master` row on the site
(one of 22), so no master record is created here.

Note on the Desk path
---------------------
Every `Pending *` state has allow_edit = "System Manager", so an ordinary
approver cannot type into "Lý do gửi lại" on the Desk form. The supported way
to send back is the "Send back" button on /approval, where the server writes the
reason and then applies this transition in one step. A Desk user who triggers
Request Changes without a reason is stopped by the `ec_*_before_save` guard with
a message pointing at /approval -- it fails closed, it does not drop a document
into Draft with no explanation.

Rollback
--------
    bench --site <site> execute \
      ecentric_workspace.approval_center.patches.p046_send_back_transitions.rollback

Idempotent: a transition is inserted only when an identical
(state, action, next_state, allowed) row is absent.
"""

import frappe

ACTION = "Request Changes"

# (workflow, state, next_state, [allowed roles])
TRANSITIONS = [
    ("MSO Approval", "Pending Manager", "Draft", ["All"]),
    ("MSO Approval", "Pending Finance", "Draft", ["EC Finance", "Administrator"]),
    ("MSO Approval", "Pending HOF", "Draft", ["EC HOF", "Administrator"]),
    ("MSO Approval", "Pending CEO", "Draft", ["EC CEO", "Administrator"]),
    ("EC SO Approval", "Pending Sales Admin", "Draft", ["EC Sales Admin", "Administrator"]),
    ("EC PO Approval", "Pending Sales Admin", "Draft", ["EC Sales Admin", "Administrator"]),
]


def _plan():
    """Group TRANSITIONS by workflow, preserving order."""
    out = {}
    for wf, state, nxt, roles in TRANSITIONS:
        out.setdefault(wf, []).append((state, nxt, roles))
    return out


def execute():
    if not frappe.db.exists("Workflow Action Master", ACTION):
        # fail-safe: never invent the master silently -- a missing master means
        # this bench is not the site this patch was written for.
        frappe.logger().info(
            "[C4b B7] Workflow Action Master '%s' missing -- skipped" % ACTION)
        return

    added_total = 0
    for wf_name, rows in _plan().items():
        if not frappe.db.exists("Workflow", wf_name):
            continue

        wf = frappe.get_doc("Workflow", wf_name)
        have_states = set(s.state for s in wf.states)
        added = 0

        for state, nxt, roles in rows:
            # Both endpoints must already be real states of THIS workflow.
            # Send back reuses `Draft`; it never creates a state.
            if state not in have_states or nxt not in have_states:
                continue

            for role in roles:
                if not frappe.db.exists("Role", role):
                    continue
                exists = False
                for t in wf.transitions:
                    if (t.state == state and t.action == ACTION
                            and t.next_state == nxt and t.allowed == role):
                        exists = True
                        break
                if exists:
                    continue
                wf.append("transitions", {
                    "state": state,
                    "action": ACTION,
                    "next_state": nxt,
                    "allowed": role,
                    # matches every existing transition on these workflows; the
                    # real identity guard is in ec_*_before_save.
                    "allow_self_approval": 1,
                })
                added += 1

        if added:
            wf.save(ignore_permissions=True)
            added_total += added
            frappe.logger().info(
                "[C4b B7] %s: +%d '%s' transition(s)" % (wf_name, added, ACTION))

    msg = "[C4b B7] send-back transitions added: %d" % added_total
    frappe.logger().info(msg)
    print(msg)


def rollback():
    """Remove exactly the transitions execute() adds. Leaves everything else."""
    removed_total = 0
    for wf_name, rows in _plan().items():
        if not frappe.db.exists("Workflow", wf_name):
            continue
        wf = frappe.get_doc("Workflow", wf_name)
        wanted = set()
        for state, nxt, roles in rows:
            for role in roles:
                wanted.add((state, ACTION, nxt, role))

        keep = [t for t in wf.transitions
                if (t.state, t.action, t.next_state, t.allowed) not in wanted]
        removed = len(wf.transitions) - len(keep)
        if not removed:
            continue
        wf.transitions = []
        for t in keep:
            wf.append("transitions", {
                "state": t.state, "action": t.action, "next_state": t.next_state,
                "allowed": t.allowed, "allow_self_approval": t.allow_self_approval,
                "condition": t.condition,
            })
        wf.save(ignore_permissions=True)
        removed_total += removed

    msg = "[C4b B7] send-back transitions removed: %d" % removed_total
    frappe.logger().info(msg)
    print(msg)
