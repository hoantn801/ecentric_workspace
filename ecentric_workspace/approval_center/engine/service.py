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
def resolve_process(approval_type, process_code=None):
    """Resolve the Active process for an approval_type. When process_code is given
    (e.g. a form selects a specific process by scope), that exact process is used -
    it must exist, be Active, and belong to approval_type. Approvers still come from
    the process participants; this only picks WHICH configured process runs."""
    if process_code:
        row = frappe.db.get_value("EC Approval Process", process_code,
                                  ["name", "status", "approval_type"], as_dict=True)
        if not row:
            frappe.throw(_("Approval process {0} not found.").format(process_code))
        if row.status != "Active":
            frappe.throw(_("Approval process {0} is not Active.").format(process_code))
        if row.approval_type != approval_type:
            frappe.throw(_("Approval process {0} does not belong to {1}.").format(process_code, approval_type))
        return frappe.get_doc("EC Approval Process", process_code)
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


def resolve_requester_department(requester, reference_doctype=None, reference_name=None):
    """Governed department snapshot for a request (reporting/historical accuracy only).

    Order (never trusts a free-text requester value):
      1) requester Employee.department (HR-governed, authoritative).
      2) the business document's `department` field IFF it resolves to a real Department.
      3) otherwise None (leave blank / Unknown - never guess).
    Fail-closed: any lookup miss returns None. Does not write anything."""
    emp = _emp_user(requester) or {}
    dept = emp.get("department")
    if dept and frappe.db.exists("Department", dept):
        return dept
    if reference_doctype and reference_name and frappe.db.has_column(reference_doctype, "department"):
        bdept = frappe.db.get_value(reference_doctype, reference_name, "department")
        if bdept and frappe.db.exists("Department", bdept):
            return bdept
    return None


def _ref_field_value(context, fieldname):
    """Read a single field off the business record named in context. Returns None on any absence
    (missing context, missing field) - fail-closed, never raises."""
    if not (context and fieldname and context.get("reference_doctype") and context.get("reference_name")):
        return None
    try:
        return frappe.db.get_value(context["reference_doctype"], context["reference_name"], fieldname)
    except Exception:
        return None


def _employee_by_ident(ident):
    """Resolve an Employee name from an email/user identifier, trying user_id then the standard
    Employee email fields. Field-absence tolerant (fail-closed)."""
    if not ident:
        return None
    for f in ("user_id", "company_email", "personal_email", "prefered_email"):
        try:
            n = frappe.db.get_value("Employee", {f: ident}, "name")
        except Exception:
            n = None
        if n:
            return n
    return None


def _manager_user_of_employee(ident):
    """Direct manager (reports_to -> user_id) of the Employee identified by an email/user. None if
    unresolvable. Generic and reusable; no hardcoded identity."""
    emp = _employee_by_ident(ident)
    if not emp:
        return None
    reports_to = frappe.db.get_value("Employee", emp, "reports_to")
    return reports_to and frappe.db.get_value("Employee", reports_to, "user_id")


def _is_active_system_user(user):
    """Fail-closed check used by all approver resolution."""
    if not user or user == "Guest":
        return False
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def resolve_department_manager_user(dept):
    """Generic, ordered resolution of a Department's responsible user (no hardcoding).
    Reusable by any 'Reference Department Head' participant and by business services.
    Order (fail-closed; each source is field-absence tolerant):
      1) Department.department_head -> Employee.user_id (if an active System User)
      2) Department.manager_email as a direct active System User
    Returns the user id, or None if nothing resolves. Backward compatible: the
    department_head path is unchanged and still wins when it resolves."""
    if not dept:
        return None
    try:
        head = frappe.db.get_value("Department", dept, "department_head")
    except Exception:
        head = None  # field absent -> fail closed
    head_user = head and frappe.db.get_value("Employee", head, "user_id")
    if head_user and _is_active_system_user(head_user):
        return head_user
    try:
        mgr_email = frappe.db.get_value("Department", dept, "manager_email")
    except Exception:
        mgr_email = None  # field absent -> fail closed
    if mgr_email and _is_active_system_user(mgr_email):
        return mgr_email
    return None


def resolve_participants(participants, requester, context=None):
    """Expand EC Approval Participant rows to a de-duplicated ordered list of
    (user, source_label). No hardcoded identities; fail-closed on unresolved."""
    out, seen = [], set()

    def _add(user, label):
        if user and user not in seen and _is_active_system_user(user):
            seen.add(user)
            out.append((user, label))

    for p in sorted(participants, key=lambda r: (r.sort_order or 0)):
        st = p.source_type
        before = len(out)
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
        elif st == "Reference Department Head":
            # Generic, config-driven: resolve the Department named in a field of the business
            # record (context) via resolve_department_manager_user (department_head first, then
            # Department.manager_email). No hardcoded department or approver.
            _add(resolve_department_manager_user(_ref_field_value(context, p.get("department_field"))),
                 "Reference Department Head")
        elif st == "Reference User Field":
            # Generic, config-driven: the approver is the User named in a field of the business
            # record (e.g. new_line_manager). No hardcoded identity; _add re-checks active System User.
            _add(_ref_field_value(context, p.get("reference_field")), "Reference User Field")
        elif st == "Reference Employee Manager":
            # Generic, config-driven: the approver is the direct manager (reports_to -> user_id) of the
            # Employee identified by the email/user in a field of the business record (e.g. employee_email).
            _add(_manager_user_of_employee(_ref_field_value(context, p.get("reference_field"))),
                 "Reference Employee Manager")
        # Per-row fallback: used ONLY when this row's primary source resolved nobody. Config-seeded
        # (never in code); _add re-checks active System User. Not a second always-on approver.
        if len(out) == before and p.get("fallback_user"):
            _add(p.get("fallback_user"), "Fallback")
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


def _drop_share_messages():
    """Remove Frappe's 'Shared with ... Read access' / assignment info messages from the request
    message_log so they never surface as popups to the end user (the actual DocShare stays)."""
    log = getattr(frappe.local, "message_log", None)
    if not log:
        return
    def _txt(m):
        if isinstance(m, str):
            return m
        if isinstance(m, dict):
            return str(m.get("message", ""))
        return str(m)
    frappe.local.message_log = [m for m in log
                                if not any(k in _txt(m) for k in ("Read access", "Shared with", "shared with"))]


def _engine_ensure_todo(doctype, name, user, description):
    """Create the next approver's/fulfiller's Open ToDo for THIS business document.
    Idempotent (skips if an Open ToDo already exists). Inserted with ignore_permissions - a
    ToDo insert never needs the acting user to hold write/share perm on the business DocType.
    assigned_by stays the real acting user (frappe.session.user) so the audit trail is honest."""
    if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name,
                                 "allocated_to": user, "status": "Open"}):
        return
    frappe.get_doc({
        "doctype": "ToDo",
        "allocated_to": user,
        "reference_type": doctype,
        "reference_name": name,
        "assigned_by": frappe.session.user,
        "description": description or _("Approval Center task"),
    }).insert(ignore_permissions=True)


def _engine_grant_read(doctype, name, user):
    """Share ONLY this one business document (read) with the next approver/fulfiller.

    Root cause of the real-user 403: the public frappe.desk.form.assign_to.add ultimately calls
    frappe.share.add(...) which runs check_share_permission against the ACTING user - and that check
    calls frappe.has_permission(ptype='share', ...) directly, which does NOT consult
    frappe.flags.ignore_permissions. So a normal approver (read access only) could not share the doc
    onward and hit 'No permission to share ...'.

    Fix: call frappe.share.add with flags={'ignore_share_permission': True} - the version-stable public
    bypass that check_share_permission itself honors. This is an ENGINE-OWNED internal share that runs
    only AFTER the actor has been authorized as a current pending approver; it grants read on exactly
    this document to exactly the snapshot-resolved next users, and touches no other document and no
    broad permission."""
    if frappe.db.exists("DocShare", {"share_doctype": doctype, "share_name": name, "user": user}):
        return
    # [COMPAT SHIM, runtime-gate finding 2026-07-12] frappe renamed the public
    # share API: newer v15 exposes add_docshare(..., flags=...) and add() no longer
    # accepts flags. Behavior identical on both; without this, any frappe upgrade
    # past the rename breaks every approval assignment.
    try:
        from frappe.share import add_docshare as _share_add  # frappe >= 15.x rename
    except ImportError:
        from frappe.share import add as _share_add  # older v15
    _share_add(doctype, name, user, read=1, flags={"ignore_share_permission": True})


def _engine_maintain_assign(doctype, name, user, add=True):
    """Keep the business doc's _assign list consistent with the live ToDos (same bookkeeping
    frappe.desk.form.assign_to does), via the ORM set_value with update_modified=False so it neither
    bumps `modified` nor requires the acting user's write perm. Not approval state - only the
    Desk 'Assigned To' metadata field."""
    cur = frappe.parse_json(frappe.db.get_value(doctype, name, "_assign") or "[]")
    if add and user not in cur:
        cur = cur + [user]
    elif (not add) and user in cur:
        cur = [x for x in cur if x != user]
    else:
        return
    frappe.db.set_value(doctype, name, "_assign", frappe.as_json(cur), update_modified=False)


def assign(doctype, name, users, description=None):
    """Assign the next approver(s)/fulfiller(s) to a business document. Idempotent (skips a user who
    already has an OPEN ToDo). Silent: mutes Frappe's share/assignment msgprints (no popups) while
    KEEPING the actual DocShare read access + ToDo. Real errors PROPAGATE so a failed assignment
    rolls back.

    ENGINE-OWNED INTERNAL OP - runs AFTER the acting approver has already been authorized (see
    approve/reject/etc.). It deliberately does NOT go through the public frappe.desk.form.assign_to.add,
    because that path shares the business doc using the ACTING user's Share permission and a normal
    approver does not hold generic Share perm on the business DocType (that would require DocPerm/System
    Manager, which we must not grant). Instead it (1) inserts the ToDo with ignore_permissions,
    (2) grants read on ONLY this document via the ignore_share_permission bypass, and (3) maintains
    _assign. It never bypasses actor authorization, never grants broad permission, and never touches
    unrelated documents. The audit actor is recorded separately by log_action; assigned_by stays the
    real acting user."""
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        for u in [x for x in dict.fromkeys(users) if x and x != "Guest"]:
            _engine_ensure_todo(doctype, name, u, description)
            _engine_grant_read(doctype, name, u)
            _engine_maintain_assign(doctype, name, u, add=True)
    finally:
        frappe.flags.mute_messages = prev_mute
    _drop_share_messages()


def close_todos(doctype, name, keep_user=None):
    """Close obsolete Open ToDos for a business document (engine-owned, after authorization).

    Cancels each obsolete Open ToDo directly with ignore_permissions and keeps _assign consistent -
    it does NOT go through frappe.desk.form.assign_to.remove, whose docshare removal also runs the
    acting user's Share-permission check (same 403 family as assign). Past approvers keep their read
    DocShare so they can still view what they acted on; only their pending task is cleared."""
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        for td in frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": name,
                                                  "status": "Open"}, fields=["name", "allocated_to"]):
            if keep_user and td.allocated_to == keep_user:
                continue
            frappe.db.set_value("ToDo", td.name, "status", "Cancelled", update_modified=False)
            _engine_maintain_assign(doctype, name, td.allocated_to, add=False)
    finally:
        frappe.flags.mute_messages = prev_mute


# --------------------------------------------------------------------------- #
# SLA
# --------------------------------------------------------------------------- #
def resolve_sla(sla_policy_code, from_dt=None, employee=None, company=None):
    """Returns {due_at, calendar, holiday_list, use_business_hours} or None.
    Calendar-hours when use_business_hours=0; otherwise the business-hours
    calculator with a resolved (and snapshot-able) Holiday List."""
    if not sla_policy_code:
        return None
    pol = frappe.db.get_value("EC Approval SLA Policy", {"policy_code": sla_policy_code, "active": 1},
        ["duration_hours", "use_business_hours", "business_calendar", "holiday_list"], as_dict=True)
    if not pol or not pol.duration_hours:
        return None
    start = from_dt or now_datetime()
    if not pol.use_business_hours:
        return {"due_at": add_to_date(start, hours=pol.duration_hours),
                "calendar": None, "holiday_list": None, "use_business_hours": 0}
    from ecentric_workspace.approval_center.engine import business_hours as bh
    from ecentric_workspace.approval_center.engine import holidays as hol
    if not pol.business_calendar:
        frappe.throw(_("SLA policy {0}: business_calendar required for business hours.").format(sla_policy_code))
    cal = frappe.get_doc("EC Approval Business Calendar", pol.business_calendar)
    hl = hol.resolve_holiday_list(employee=employee, company=company, override=pol.holiday_list)
    if not hl:
        frappe.throw(_("SLA policy {0}: no resolvable Holiday List for business-hours SLA.").format(sla_policy_code))
    due = bh.calculate_business_due_at(start, pol.duration_hours,
                                       bh.build_periods(cal.working_periods), hol.holiday_dates(hl))
    return {"due_at": due, "calendar": pol.business_calendar, "holiday_list": hl, "use_business_hours": 1}


def compute_due_at(sla_policy_code, from_dt=None, employee=None, company=None):
    r = resolve_sla(sla_policy_code, from_dt, employee, company)
    return r["due_at"] if r else None


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
            "source_process_level": lvl.name, "sla_policy": lvl.sla_policy,
            "allows_amount_adjustment": lvl.allows_amount_adjustment, "level_status": "Pending",
        }).insert(ignore_permissions=True)
        approvers = resolve_participants(
            [p for p in lvl.participants if p.participant_purpose == "Approver"], requester,
            context={"reference_doctype": req.reference_doctype, "reference_name": req.reference_name})
        if not approvers:
            frappe.throw(_("No approver resolved for level {0} ({1}). Submission blocked.").format(
                lvl.level_no, lvl.level_name))
        for user, label in approvers:
            frappe.get_doc({
                "doctype": "EC Approval Request Approver", "approval_request": req.name,
                "request_level": rl.name, "level_no": lvl.level_no, "approver": user,
                "source": label, "status": "Pending",
            }).insert(ignore_permissions=True)


def submit(reference_doctype, reference_name, approval_type, requester, process_code=None,
           activate_first_level=True):
    process = resolve_process(approval_type, process_code)
    levels = resolve_levels(process.name)
    if not levels:
        frappe.throw(_("Process {0} has no levels.").format(process.name))
    req = frappe.get_doc({
        "doctype": "EC Approval Request", "approval_type": approval_type,
        "reference_doctype": reference_doctype, "reference_name": reference_name,
        "approval_process": process.name, "process_version": process.version_no,
        "requested_by": requester, "submitted_at": now_datetime(),
        "requester_department": resolve_requester_department(requester, reference_doctype, reference_name),
        "approval_status": "Pending", "current_level": 0,
    }).insert(ignore_permissions=True)
    build_snapshot(req, process, levels, requester)
    log_action(req.name, "Submitted", requester, new_status="Pending")
    # Deferred activation (Option B): a governed pre-approval step (e.g. requester signing)
    # may need to complete first. When activate_first_level is False the request + frozen
    # snapshot exist but Level 1 is NOT activated (no ToDo, no approver notification) until
    # that step confirms success. The default True preserves every existing flow.
    if activate_first_level:
        first = _request_levels(req.name)[0]
        _activate_level(req, first.level_no)
    return req.name


def _level_pending_approvers(req_name, level_no):
    return frappe.get_all("EC Approval Request Approver",
                          filters={"approval_request": req_name, "level_no": level_no, "status": "Pending"},
                          fields=["name", "approver"])


def _approved_earlier_level(req_name, approver, level_no):
    """True if this approver already has an Approved decision at an EARLIER level of the SAME request."""
    return bool(frappe.db.exists("EC Approval Request Approver",
                                 {"approval_request": req_name, "approver": approver,
                                  "status": "Approved", "level_no": ["<", level_no]}))


def _all_level_approvers_already_approved(req_name, level_no):
    """Duplicate-approver rule (Any-One safe): True ONLY if the level has pending approvers AND every one
    of them has already approved an earlier level in this request. If even one pending approver has not
    approved earlier, returns False so the level stays active for that person. L1 can never match."""
    pending = _level_pending_approvers(req_name, level_no)
    if not pending:
        return False
    return all(_approved_earlier_level(req_name, ap.approver, level_no) for ap in pending)


def _auto_skip_duplicate_level(req, level_no):
    """Skip a level whose approvers ALL already approved an earlier level, during activation/advance.
    Marks each pending approver row + the level as skipped, records an auditable EC Approval Action per
    approver (action=Skipped, with the duplicate-approver reason), then advances to the next level or
    completes the request. The level never receives a redundant ToDo/DocShare. No DocPerm change, no Admin
    bypass, no raw status mutation outside the engine; the approver rows are preserved (status Skipped)."""
    rl = _rl_for(req.name, level_no)
    now = now_datetime()
    for ap in _level_pending_approvers(req.name, level_no):
        frappe.db.set_value("EC Approval Request Approver", ap.name,
                            {"status": "Skipped", "decided_at": now})
        log_action(req.name, "Skipped", "Administrator", level_no, level_name=rl.level_name,
                   comment=_("Skipped because all approvers already approved an earlier level"),
                   related_user=ap.approver, previous_status="Pending", new_status="Skipped")
    # Level marked Approved (passed) - same shape the Any-One skip-remaining path uses, so the frontend
    # renders it gracefully; the per-approver Skipped rows + audit action record the duplicate skip.
    frappe.db.set_value("EC Approval Request Level", rl.name,
                        {"level_status": "Approved", "activated_at": now, "completed_at": now})
    frappe.db.set_value("EC Approval Request", req.name, "current_level", level_no)
    nxt = [l for l in _request_levels(req.name) if l.level_no > level_no]
    if nxt:
        _activate_level(frappe.get_doc("EC Approval Request", req.name), nxt[0].level_no)
    else:
        complete_approval(frappe.get_doc("EC Approval Request", req.name))


def _activate_level(req, level_no):
    # Governance: duplicate-approver auto-skip. When a level becomes active, if EVERY pending approver has
    # already approved an earlier level in this same request, skip it (audited) and advance instead of
    # asking the same person to approve twice. Runs only at activation/advance (never before), never skips
    # L1 (no earlier level), and never fires while any non-duplicate approver is still pending (Any-One safe).
    if _all_level_approvers_already_approved(req.name, level_no):
        _auto_skip_duplicate_level(req, level_no)
        return
    rl = _rl_for(req.name, level_no)
    rl.level_status = "In Progress"
    rl.activated_at = now_datetime()
    _emp = frappe.db.get_value("Employee", {"user_id": req.requested_by}, ["name", "company"], as_dict=True)
    sla = resolve_sla(rl.sla_policy, rl.activated_at,
                      employee=_emp.name if _emp else None, company=_emp.company if _emp else None)
    if sla:
        rl.due_at = sla["due_at"]; rl.sla_calendar = sla["calendar"]; rl.sla_holiday_list = sla["holiday_list"]
    rl.save(ignore_permissions=True)
    frappe.db.set_value("EC Approval Request", req.name, "current_level", level_no)
    approvers = frappe.get_all("EC Approval Request Approver",
                               filters={"approval_request": req.name, "level_no": level_no, "status": "Pending"},
                               pluck="approver")
    notify(approvers, _("Approval needed: {0}").format(req.name), req.reference_doctype, req.reference_name)
    close_todos(req.reference_doctype, req.reference_name)   # close prior-level ToDos before assigning the new level
    assign(req.reference_doctype, req.reference_name, approvers,
           _("Approval level {0}").format(level_no))


def _actor_pending_row(req_name, level_no, actor):
    n = frappe.get_all("EC Approval Request Approver",
                       filters={"approval_request": req_name, "level_no": level_no,
                                "approver": actor, "status": "Pending"}, pluck="name")
    return n[0] if n else None


def _signature_guard(req, level_no, actor):
    """[esign S2A, 2026-07-11] Signature-required levels complete ONLY through the
    governed verified-signature path: esign.guard validates a PERSISTED, provider-
    verified EC Digital Signature Request against the DB under row lock (frappe.flags
    is a call marker only, never authorization). Applies to EVERY caller including
    admin override - NO role bypass, NO break-glass in S2A (user directive).
    Fail-closed: an import/runtime error blocks approval rather than silently
    allowing an unsigned completion. Types without an enabled+gated signing profile:
    one indexed query, behavior unchanged."""
    from ecentric_workspace.approval_center.esign import guard as esign_guard
    esign_guard.assert_level_completable(req, level_no, actor)


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
    _signature_guard(req, req.current_level, actor)
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
                        {"approval_status": "Pending", "information_requested_from_level": 0})   # Int NOT NULL: clear with 0, never None
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


# Generic post-final-approval fulfillment dispatch. Keyed by business DocType ->
# dotted "module.service.on_final_approval" (a handler path in config, NOT approver
# identities). Additive: forms opt in by adding an entry; engine flow is unchanged
# for types without a handler. Approvers/fulfillers still come from process config.
_FULFILLMENT_HANDLERS = {
    "EC AI Topup Request": "ecentric_workspace.approval_center.ai_topup.service.on_final_approval",
    "EC Data Request": "ecentric_workspace.approval_center.data_request.service.on_final_approval",
    "EC Document Request": "ecentric_workspace.approval_center.document_request.service.on_final_approval",
    "EC System Request": "ecentric_workspace.approval_center.system_request.service.on_final_approval",
    "EC Asset Request": "ecentric_workspace.approval_center.asset_request.service.on_final_approval",
    "EC Resignation Request": "ecentric_workspace.approval_center.resignation.service.on_final_approval",
}


def complete_approval(req):
    frappe.db.set_value("EC Approval Request", req.name,
                        {"approval_status": "Approved", "current_level": 0, "completed_at": now_datetime()})
    log_action(req.name, "Approved", "Administrator", comment=_("All levels approved"), new_status="Approved")
    close_todos(req.reference_doctype, req.reference_name)
    handler = _FULFILLMENT_HANDLERS.get(req.reference_doctype)
    if handler:
        frappe.get_attr(handler)(req.reference_name)


def admin_override_current_level(request_name, actor=None, reason=None):
    """System Manager override: force-approve ONLY the current pending level, advancing via the
    same completion path as a normal approval. Composes existing primitives (no change to the normal
    approve/reject flow). Does NOT impersonate the original approvers - they are marked Skipped and
    the audit records the real actor. Only the current level is approved (never a skip-all)."""
    actor = actor or frappe.session.user
    if not (reason or "").strip():
        frappe.throw(_("A reason is mandatory for an admin override."))
    req = frappe.get_doc("EC Approval Request", request_name)
    _guard_open(req)
    if req.approval_status != "Pending":
        frappe.throw(_("Admin override is only allowed while the request is pending approval."))
    level_no = req.current_level
    if not level_no:
        frappe.throw(_("There is no current approval level to override."))
    frappe.db.get_value("EC Approval Request", request_name, "name", for_update=True)   # row lock
    rl = _rl_for(request_name, level_no)
    if not rl or rl.level_status != "In Progress":
        frappe.throw(_("The current level is not pending; please refresh."))
    frappe.db.get_value("EC Approval Request Level", rl.name, "name", for_update=True)
    # [esign S2A] Admin override is NOT exempt: a signature-required level cannot be
    # force-approved by any role (no break-glass in S2A - user directive 2026-07-11).
    _signature_guard(req, level_no, actor)
    skip_note = _("Admin override approved by {0}").format(actor)
    for ap in frappe.get_all("EC Approval Request Approver",
                             filters={"approval_request": request_name, "level_no": level_no, "status": "Pending"},
                             fields=["name", "approver"]):
        frappe.db.set_value("EC Approval Request Approver", ap.name,
                            {"status": "Skipped", "decided_at": now_datetime(), "comment": skip_note})
        log_action(request_name, "Skipped", actor, level_no, comment=skip_note,
                   related_user=ap.approver, new_status="Skipped")
    log_action(request_name, "Approved", actor, level_no,
               comment=_("Admin override approve. Reason: {0}").format(reason),
               previous_status="Pending", new_status="Approved")
    frappe.db.set_value("EC Approval Request Level", rl.name,
                        {"level_status": "Approved", "completed_at": now_datetime()})
    nxt = [l for l in _request_levels(request_name) if l.level_no > level_no]
    if nxt:
        _activate_level(frappe.get_doc("EC Approval Request", request_name), nxt[0].level_no)
    else:
        complete_approval(frappe.get_doc("EC Approval Request", request_name))
