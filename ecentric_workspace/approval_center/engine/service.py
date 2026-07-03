# Copyright (c) 2026, eCentric and contributors
"""Generic Approval Center orchestration service (reusable across approval types).

Sources of truth: EC Approval Process/Level/Participant (config), EC Approval
Request (+ snapshot Level/Approver rows) (runtime state), EC Approval Action
(append-only audit). All writes go through here; permission is enforced per
operation. Snapshots are frozen at submit so later config edits never alter
in-flight requests.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date

OPEN_STATUSES = ("Pending", "Information Required")
TERMINAL = ("Approved", "Rejected", "Cancelled")


# --------------------------------------------------------------------------- #
# PURE level-completion decision (no DB) - exhaustively unit-testable.
# statuses: list of runtime approver statuses for the active level.
# Returns (decision, skip_remaining): decision in {"approved","rejected","pending"}.
# --------------------------------------------------------------------------- #
def decide_level(mode, minimum_approvals, statuses):
    if "Rejected" in statuses:
        return ("rejected", False)
    approved = sum(1 for s in statuses if s == "Approved")
    total = len(statuses)
    if mode == "Any One":
        if approved >= 1:
            return ("approved", True)   # skip remaining pending
    elif mode == "All Required":
        if total and approved == total:
            return ("approved", False)
    elif mode == "Minimum Count":
        if approved >= (minimum_approvals or 0) and (minimum_approvals or 0) > 0:
            return ("approved", True)
    return ("pending", False)


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def resolve_process(approval_type):
    rows = frappe.get_all("EC Approval Process",
                          filters={"approval_type": approval_type, "status": "Active"},
                          fields=["name"], limit_page_length=1)
    if not rows:
        frappe.throw(_("No Active approval process configured for {0}.").format(approval_type))
    return frappe.get_doc("EC Approval Process", rows[0].name)


def resolve_levels(process_name):
    names = frappe.get_all("EC Approval Level", filters={"approval_process": process_name},
                           fields=["name", "level_no"], order_by="level_no asc")
    return [frappe.get_doc("EC Approval Level", n.name) for n in names]


def _emp_user(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "reports_to", "department"], as_dict=True)


def _is_active_system_user(user):
    """Fail-closed check used by all approver resolution."""
    if not user or user == "Guest":
        return False
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def resolve_participants(participants, requester):
    """Expand EC Approval Participant rows to a de-duplicated ordered list of
    (user, source_label). No hardcoded identities; fail-closed on unresolved."""
    out, seen = [], set()

    def _add(user, label):
        if user and user not in seen and _is_active_system_user(user):
            seen.add(user)
            out.append((user, label))

    for p in sorted(participants, key=lambda r: (r.sort_order or 0)):
        st = p.source_type
        if st == "User":
            _add(p.user, "Configured User")
        elif st == "Role":
            for u in frappe.get_all("Has Role", filters={"role": p.role, "parenttype": "User"},
                                    fields=["parent"], distinct=True):
                _add(u.parent, "Role: %s" % p.role)
        elif st == "Requester Manager":
            emp = _emp_user(requester)
            mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
            _add(mgr, "Requester Manager")
        elif st == "Department Manager":
            dept = p.department or (_emp_user(requester) or {}).get("department")
            head_user = None
            if dept:
                try:
                    head = frappe.db.get_value("Department", dept, "department_head")
                except Exception:
                    head = None  # field absent -> fail closed
                head_user = head and frappe.db.get_value("Employee", head, "user_id")
            _add(head_user, "Department Manager")  # _add re-checks active System User
    return out


# --------------------------------------------------------------------------- #
# Audit + notify + assignment helpers
# --------------------------------------------------------------------------- #
def log_action(request_name, action, actor, level_no=None, level_name=None, comment=None,
               previous_status=None, new_status=None, related_user=None):
    seq = (frappe.db.count("EC Approval Action", {"approval_request": request_name}) or 0) + 1
    frappe.get_doc({
        "doctype": "EC Approval Action", "approval_request": request_name, "seq": seq,
        "level_no": level_no, "level_name": level_name, "actor": actor or frappe.session.user,
        "action": action, "comment": comment, "action_time": now_datetime(),
        "previous_status": previous_status, "new_status": new_status, "related_user": related_user,
    }).insert(ignore_permissions=True)


def notify(users, subject, doctype, name):
    for u in set(u for u in users if u and u != "Guest"):
        try:
            frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert",
                            "subject": subject, "document_type": doctype, "document_name": name}
                           ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="approval_center notify failed")


def assign(doctype, name, users, description=None):
    """Canonical Frappe assignment (frappe.desk.form.assign_to.add). Idempotent:
    skips a user who already has an OPEN ToDo, so no duplicate open assignment.
    Real errors PROPAGATE so a failed assignment rolls back the transaction."""
    from frappe.desk.form.assign_to import add as _add
    for u in [x for x in dict.fromkeys(users) if x and x != "Guest"]:
        if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name,
                                     "allocated_to": u, "status": "Open"}):
            continue
        _add({"assign_to": [u], "doctype": doctype, "name": name,
              "description": description or _("Approval Center task")})


def close_todos(doctype, name, keep_user=None):
    """Close obsolete assignments via the canonical helper
    (frappe.desk.form.assign_to.remove) so _assign + the audit comment stay
    consistent - not raw ToDo mutation."""
    from frappe.desk.form.assign_to import remove as _remove
    for td in frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": name,
                                              "status": "Open"}, fields=["allocated_to"]):
        if keep_user and td.allocated_to == keep_user:
            continue
        _remove(doctype, name, td.allocated_to)


# --------------------------------------------------------------------------- #
# SLA
# --------------------------------------------------------------------------- #
def compute_due_at(sla_policy_code, from_dt=None):
    if not sla_policy_code:
        return None
    hours = frappe.db.get_value("EC Approval SLA Policy",
                                {"policy_code": sla_policy_code, "active": 1}, "duration_hours")
    if not hours:
        return None
    return add_to_date(from_dt or now_datetime(), hours=hours)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _request_levels(req_name):
    return frappe.get_all("EC Approval Request Level", filters={"approval_request": req_name},
                          fields=["name", "level_no"], order_by="level_no asc")


def _rl_for(req_name, level_no):
    n = frappe.get_all("EC Approval Request Level",
                       filters={"approval_request": req_name, "level_no": level_no}, pluck="name")
    return frappe.get_doc("EC Approval Request Level", n[0]) if n else None


def _guard_open(req):
    if req.approval_status in TERMINAL:
        frappe.throw(_("Request is {0}; no further action is allowed.").format(req.approval_status))


def build_snapshot(req, process, levels, requester):
    for lvl in levels:
        rl = frappe.get_doc({
            "doctype": "EC Approval Request Level", "approval_request": req.name,
            "level_no": lvl.level_no, "level_name": lvl.level_name, "approval_mode": lvl.approval_mode,
            "minimum_approvals": lvl.minimum_approvals, "mandatory": lvl.mandatory,
            "source_process_level": lvl.name, "sla_policy": lvl.sla_policy, "level_status": "Pending",
        }).insert(ignore_permissions=True)
        approvers = resolve_participants(
            [p for p in lvl.participants if p.participant_purpose == "Approver"], requester)
        if not approvers:
            frappe.throw(_("No approver resolved for level {0} ({1}). Submission blocked.").format(
                lvl.level_no, lvl.level_name))
        for user, label in approvers:
            frappe.get_doc({
                "doctype": "EC Approval Request Approver", "approval_request": req.name,
                "request_level": rl.name, "level_no": lvl.level_no, "approver": user,
                "source": label, "status": "Pending",
            }).insert(ignore_permissions=True)


def submit(reference_doctype, reference_name, approval_type, requester):
    process = resolve_process(approval_type)
    levels = resolve_levels(process.name)
    if not levels:
        frappe.throw(_("Process {0} has no levels.").format(process.name))
    req = frappe.get_doc({
        "doctype": "EC Approval Request", "approval_type": approval_type,
        "reference_doctype": reference_doctype, "reference_name": reference_name,
        "approval_process": process.name, "process_version": process.version_no,
        "requested_by": requester, "submitted_at": now_datetime(),
        "approval_status": "Pending", "current_level": 0,
    }).insert(ignore_permissions=True)
    build_snapshot(req, process, levels, requester)
    log_action(req.name, "Submitted", requester, new_status="Pending")
    first = _request_levels(req.name)[0]
    _activate_level(req, first.level_no)
    return req.name


def _activate_level(req, level_no):
    rl = _rl_for(req.name, level_no)
    rl.level_status = "In Progress"
    rl.activated_at = now_datetime()
    rl.due_at = compute_due_at(rl.sla_policy, rl.activated_at)
    rl.save(ignore_permissions=True)
    frappe.db.set_value("EC Approval Request", req.name, "current_level", level_no)
    approvers = frappe.get_all("EC Approval Request Approver",
                               filters={"approval_request": req.name, "level_no": level_no, "status": "Pending"},
                               pluck="approver")
    notify(approvers, _("Approval needed: {0}").format(req.name), req.reference_doctype, req.reference_name)
    assign(req.reference_doctype, req.reference_name, approvers,
           _("Approval level {0}").format(level_no))


def _actor_pending_row(req_name, level_no, actor):
    n = frappe.get_all("EC Approval Request Approver",
                       filters={"approval_request": req_name, "level_no": level_no,
                                "approver": actor, "status": "Pending"}, pluck="name")
    return n[0] if n else None


def approve(request_name, actor=None, comment=None):
    actor = actor or frappe.session.user
    req = frappe.get_doc("EC Approval Request", request_name)
    _guard_open(req)
    frappe.db.get_value("EC Approval Request", request_name, "name", for_update=True)  # row lock
    if req.current_level:
        _lk = _rl_for(request_name, req.current_level)
        _lk and frappe.db.get_value("EC Approval Request Level", _lk.name, "name", for_update=True)
    row = _actor_pending_row(request_name, req.current_level, actor)
    if not row:
        frappe.throw(_("You are not a pending approver for the current level."))
    frappe.db.set_value("EC Approval Request Approver", row,
                        {"status": "Approved", "decided_at": now_datetime(), "comment": comment})
    log_action(request_name, "Approved", actor, req.current_level, comment=comment)
    _evaluate(req, req.current_level)


def reject(request_name, actor=None, comment=None):
    actor = actor or frappe.session.user
    if not (comment or "").strip():
        frappe.throw(_("A rejection reason is mandatory."))
    req = frappe.get_doc("EC Approval Request", request_name)
    _guard_open(req)
    frappe.db.get_value("EC Approval Request", request_name, "name", for_update=True)
    if req.current_level:
        _lk = _rl_for(request_name, req.current_level)
        _lk and frappe.db.get_value("EC Approval Request Level", _lk.name, "name", for_update=True)
    row = _actor_pending_row(request_name, req.current_level, actor)
    if not row:
        frappe.throw(_("You are not a pending approver for the current level."))
    frappe.db.set_value("EC Approval Request Approver", row,
                        {"status": "Rejected", "decided_at": now_datetime(), "comment": comment})
    log_action(request_name, "Rejected", actor, req.current_level, comment=comment,
               previous_status="Pending", new_status="Rejected")
    rl = _rl_for(request_name, req.current_level)
    rl.level_status = "Rejected"; rl.save(ignore_permissions=True)
    frappe.db.set_value("EC Approval Request", request_name,
                        {"approval_status": "Rejected", "completed_at": now_datetime()})
    close_todos(req.reference_doctype, req.reference_name)
    notify([req.requested_by], _("Request rejected: {0}").format(request_name),
           req.reference_doctype, req.reference_name)


def request_information(request_name, actor=None, comment=None):
    actor = actor or frappe.session.user
    if not (comment or "").strip():
        frappe.throw(_("A comment is mandatory when requesting information."))
    req = frappe.get_doc("EC Approval Request", request_name)
    _guard_open(req)
    row = _actor_pending_row(request_name, req.current_level, actor)
    if not row:
        frappe.throw(_("You are not a pending approver for the current level."))
    frappe.db.set_value("EC Approval Request Approver", row,
                        {"status": "Information Requested", "decided_at": now_datetime(), "comment": comment})
    log_action(request_name, "Information Requested", actor, req.current_level, comment=comment,
               previous_status="Pending", new_status="Information Required")
    frappe.db.set_value("EC Approval Request", request_name,
                        {"approval_status": "Information Required",
                         "information_requested_from_level": req.current_level})
    close_todos(req.reference_doctype, req.reference_name)
    notify([req.requested_by], _("Information requested: {0}").format(request_name),
           req.reference_doctype, req.reference_name)


def resubmit(request_name, actor=None, restart=False):
    req = frappe.get_doc("EC Approval Request", request_name)
    if req.approval_status not in ("Information Required",) and not restart:
        frappe.throw(_("Only an Information Required request can be resubmitted."))
    resume = 1 if restart else (req.information_requested_from_level or 1)
    for rl in _request_levels(request_name):
        if rl.level_no >= resume:
            frappe.db.set_value("EC Approval Request Level", rl.name,
                                {"level_status": "Pending", "activated_at": None,
                                 "completed_at": None, "due_at": None})
            for ap in frappe.get_all("EC Approval Request Approver",
                                     filters={"approval_request": request_name, "level_no": rl.level_no}, pluck="name"):
                frappe.db.set_value("EC Approval Request Approver", ap,
                                    {"status": "Pending", "decided_at": None, "comment": None})
    frappe.db.set_value("EC Approval Request", request_name,
                        {"approval_status": "Pending", "information_requested_from_level": None})
    log_action(request_name, "Restarted" if restart else "Resubmitted", actor or req.requested_by,
               resume, comment=_("Restarted from level 1 (material change)") if restart else None,
               new_status="Pending")
    _activate_level(frappe.get_doc("EC Approval Request", request_name), resume)


def cancel(request_name, actor=None, reason=None):
    if not (reason or "").strip():
        frappe.throw(_("A cancellation reason is mandatory."))
    req = frappe.get_doc("EC Approval Request", request_name)
    _guard_open(req)
    frappe.db.set_value("EC Approval Request", request_name,
                        {"approval_status": "Cancelled", "completed_at": now_datetime()})
    log_action(request_name, "Cancelled", actor or frappe.session.user, req.current_level,
               comment=reason, new_status="Cancelled")
    close_todos(req.reference_doctype, req.reference_name)
    notify([req.requested_by], _("Request cancelled: {0}").format(request_name),
           req.reference_doctype, req.reference_name)


def _evaluate(req, level_no):
    statuses = frappe.get_all("EC Approval Request Approver",
                              filters={"approval_request": req.name, "level_no": level_no}, pluck="status")
    rl = _rl_for(req.name, level_no)
    decision, skip_remaining = decide_level(rl.approval_mode, rl.minimum_approvals, statuses)
    if decision == "rejected":
        return  # reject() already handled the terminal transition
    if decision != "approved":
        return
    if skip_remaining:
        for ap in frappe.get_all("EC Approval Request Approver",
                                 filters={"approval_request": req.name, "level_no": level_no, "status": "Pending"},
                                 fields=["name", "approver"]):
            frappe.db.set_value("EC Approval Request Approver", ap.name,
                                {"status": "Skipped", "decided_at": now_datetime()})
            log_action(req.name, "Skipped", "Administrator", level_no,
                       comment=_("Level already approved"), related_user=ap.approver, new_status="Skipped")
    frappe.db.set_value("EC Approval Request Level", rl.name,
                        {"level_status": "Approved", "completed_at": now_datetime()})
    nxt = [l for l in _request_levels(req.name) if l.level_no > level_no]
    if nxt:
        _activate_level(frappe.get_doc("EC Approval Request", req.name), nxt[0].level_no)
    else:
        complete_approval(frappe.get_doc("EC Approval Request", req.name))


def complete_approval(req):
    frappe.db.set_value("EC Approval Request", req.name,
                        {"approval_status": "Approved", "current_level": 0, "completed_at": now_datetime()})
    log_action(req.name, "Approved", "Administrator", comment=_("All levels approved"), new_status="Approved")
    close_todos(req.reference_doctype, req.reference_name)
    if req.reference_doctype == "EC AI Topup Request":
        from ecentric_workspace.approval_center.ai_topup import service as ai
        ai.on_final_approval(req.reference_name)
