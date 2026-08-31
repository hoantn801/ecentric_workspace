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
from frappe.utils import now_datetime, add_to_date, getdate

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
            # Static form: the named department. Dynamic form (department empty): the
            # requester's own department. Managers' Employee.department is the
            # "Management - EC" reporting group (PnL gate), NOT their real department -
            # so prefer the department the requester MANAGES (Department.manager_email),
            # then fall back to Employee.department (correct for regular staff).
            dept = p.department
            if not dept:
                try:
                    dept = frappe.db.get_value(
                        "Department", {"manager_email": requester, "disabled": 0}, "name")
                except Exception:
                    dept = None  # field absent -> fail closed
            if not dept:
                dept = (_emp_user(requester) or {}).get("department")
            # Ordered resolution: department_head -> manager_email (active System User only).
            _add(resolve_department_manager_user(dept), "Department Manager")
            # Khong tra ra ai -> lay nguoi ma NGUOI DE NGHI DA CHON, doc tu mot truong tren
            # chinh phieu (cau hinh o `reference_field` cua dong nay). Khong chon thi khong
            # co ai, va build_snapshot chan viec gui - dung nhu Hoan chot 28/08: "cho chon 1
            # trong nhung truong phong thoi", "con khong thi chan duyet roi doi gan truong
            # phong".
            #
            # KHONG mo cho ca nhom. Phuong an do da can nhac va bi bac: no bien Cap 1 thanh
            # "bat ky truong phong nao cung duyet duoc cho bat ky phong nao".
            if len(out) == before and p.get("reference_field"):
                _add(_ref_field_value(context, p.get("reference_field")),
                     "Chosen Department Head")
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


def request_label(reference_doctype, reference_name, approval_type=None):
    """Human-friendly label for a request in notifications. Returns the reference doc's
    title (its DocType title_field, e.g. request_title -> 'De nghi top up AI - Higgsfield')
    so Teams/inbox cards show a meaningful name instead of the opaque record id. Falls back
    to '<Type label> <id>' then the id. Never raises (notification text must not break a txn)."""
    title = ""
    try:
        meta = frappe.get_meta(reference_doctype)
        tf = getattr(meta, "title_field", None)
        if tf:
            title = frappe.db.get_value(reference_doctype, reference_name, tf) or ""
    except Exception:
        title = ""
    if title:
        return title
    label = ""
    if approval_type:
        label = frappe.db.get_value("EC Approval Type", approval_type, "approval_title") or ""
    return ("{0} {1}".format(label, reference_name)).strip() if label else (reference_name or "")


_AMOUNT_FIELDS = ("payment_amount", "requested_amount", "total_amount", "amount",
                  "approved_amount", "budget")


def request_summary(reference_doctype, reference_name):
    """One-line notification body: sender + department + amount (best-effort). Meta-driven
    so it never reads a missing field; returns '' on any error (notif text must not break a
    txn). Joined with a middot into a single line so it renders across all channels."""
    try:
        meta = frappe.get_meta(reference_doctype)
        fnames = set(df.fieldname for df in meta.fields)
    except Exception:
        return ""
    wanted = [f for f in ("requested_by", "department", "requester_department") if f in fnames]
    amount_field = next((f for f in _AMOUNT_FIELDS if f in fnames), None)
    fields = wanted + ([amount_field] if amount_field else [])
    if not fields:
        return ""
    row = frappe.db.get_value(reference_doctype, reference_name, fields, as_dict=True) or {}
    parts = []
    sender = row.get("requested_by")
    if sender:
        parts.append("Người gửi: " + (frappe.db.get_value("User", sender, "full_name") or sender))
    dept = row.get("department") or row.get("requester_department")
    if dept:
        parts.append("Phòng ban: " + str(dept))
    if amount_field and row.get(amount_field):
        try:
            parts.append("Số tiền: " + "{:,.0f} VND".format(float(row.get(amount_field))))
        except (TypeError, ValueError):
            pass
    return " · ".join(parts)


def notify(users, subject, doctype, name):
    """Publish an approval notification to each recipient through the notification_center
    pipeline (events.publish_notification_event). That single path owns the in-app Notification
    Log AND fans out to Microsoft Teams via the working 'eCentric Copilot' channel, honouring each
    user's EC Notification Preference / quiet hours. event_type 'approval_required' routes to Teams
    by default. A unique dedupe_key per call preserves the historical always-notify behaviour (no
    accidental suppression of distinct approval events on the same request)."""
    from ecentric_workspace.notification_center import events as ncev
    action_url = _approval_link(doctype, name)
    message = request_summary(doctype, name)
    stamp = now_datetime().strftime("%Y%m%d%H%M%S%f")
    for u in set(u for u in users if u and u != "Guest"):
        try:
            ncev.publish_notification_event(
                "approval_required", u, subject or "", message=message, action_url=action_url,
                reference_doctype=doctype, reference_name=name,
                dedupe_key="|".join([doctype or "", name or "", u, stamp]))
        except Exception:
            frappe.log_error(title="approval_center notify failed")


def _approval_link(doctype, name):
    """Deep link to the request in its form page: <site>/<type route>?id=<business name>. None if
    the type has no published route. Used as the Teams card 'open' action."""
    try:
        atype = frappe.db.get_value(doctype, name, "approval_type")
        if not atype:
            # The business doc often has no approval_type on the record, AND its
            # approval_request back-link is not set yet at notify time (set after
            # _activate_level). Reverse-lookup the EC Approval Request BY REFERENCE
            # (authoritative, same type source as reporting/feed) so the deep link is
            # populated even during submit -- root cause of blank 'Link:' Teams cards.
            atype = frappe.db.get_value(
                "EC Approval Request",
                {"reference_doctype": doctype, "reference_name": name},
                "approval_type")
        route = frappe.db.get_value("EC Approval Type", atype, "route") if atype else None
        if not route:
            return None
        route = route if route.startswith("/") else "/" + route
        return frappe.utils.get_url() + route + "?id=" + name
    except Exception:
        return None


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


#: stable marker (Custom Field on ToDo, created by patch p044) distinguishing
#: FULFILLMENT-stage tasks from approval-stage or unrelated tasks on the same
#: business document. Every fulfillment lifecycle op is scoped to this flag so an
#: unrelated Open ToDo on the same document is NEVER touched.
FULFILLMENT_MARKER = "ec_fulfillment"


def _engine_ensure_todo(doctype, name, user, description, date=None, fulfillment=False):
    """Create the next approver's/fulfiller's Open ToDo for THIS business document.
    Idempotent (skips if an Open ToDo already exists). Inserted with ignore_permissions - a
    ToDo insert never needs the acting user to hold write/share perm on the business DocType.
    assigned_by stays the real acting user (frappe.session.user) so the audit trail is honest.
    `date` (optional) is written to ToDo.date -- callers pass the governed SLA due (e.g. a
    fulfillment producer passes fulfillment_due_at) so the task carries its own due date.
    `fulfillment=True` stamps the stable FULFILLMENT_MARKER so lifecycle ops can scope to it."""
    if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name,
                                 "allocated_to": user, "status": "Open"}):
        return
    todo = {
        "doctype": "ToDo",
        "allocated_to": user,
        "reference_type": doctype,
        "reference_name": name,
        "assigned_by": frappe.session.user,
        "description": description or _("Approval Center task"),
    }
    if date:
        todo["date"] = date
    if fulfillment:
        todo[FULFILLMENT_MARKER] = 1
    frappe.get_doc(todo).insert(ignore_permissions=True)


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


def assign(doctype, name, users, description=None, date=None, fulfillment=False):
    """Assign the next approver(s)/fulfiller(s) to a business document. Idempotent (skips a user who
    already has an OPEN ToDo). Silent: mutes Frappe's share/assignment msgprints (no popups) while
    KEEPING the actual DocShare read access + ToDo. Real errors PROPAGATE so a failed assignment
    rolls back. `date` (optional) sets ToDo.date on newly created tasks -- fulfillment producers
    pass fulfillment_due_at so the pool ToDos carry the governed due date. `fulfillment=True`
    stamps the FULFILLMENT_MARKER so lifecycle ops scope to fulfillment tasks only.

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
            _engine_ensure_todo(doctype, name, u, description, date, fulfillment)
            _engine_grant_read(doctype, name, u)
            _engine_maintain_assign(doctype, name, u, add=True)
    finally:
        frappe.flags.mute_messages = prev_mute
    _drop_share_messages()


def close_fulfillment_todos(doctype, name, keep_user=None):
    """Close Open FULFILLMENT ToDos (FULFILLMENT_MARKER=1) for a business document,
    optionally keeping `keep_user`'s. SCOPED: an unrelated Open ToDo on the same
    document (no marker) is NEVER touched."""
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        for td in frappe.get_all("ToDo", filters={
                "reference_type": doctype, "reference_name": name, "status": "Open",
                FULFILLMENT_MARKER: 1}, fields=["name", "allocated_to"]):
            if keep_user and td.allocated_to == keep_user:
                continue
            frappe.db.set_value("ToDo", td.name, "status", "Cancelled", update_modified=False)
            _engine_maintain_assign(doctype, name, td.allocated_to, add=False)
    finally:
        frappe.flags.mute_messages = prev_mute


def _as_date(v):
    """Date-only normalization for write-idempotent ToDo.date comparison; None-safe."""
    if not v:
        return None
    try:
        return getdate(v)
    except Exception:
        return str(v)[:10]


def _ensure_fulfillment_todo(doctype, name, user, description, date=None):
    """Guarantee `user` has exactly one OPEN, MARKED fulfillment ToDo and that its
    date == `date`. If the user already has an Open ToDo on the document, it is
    UPGRADED in place (marker set, date re-stamped to the governed fulfillment_due_at)
    -- never a duplicate. Otherwise a marked ToDo is created."""
    existing = frappe.get_all("ToDo", filters={
        "reference_type": doctype, "reference_name": name,
        "allocated_to": user, "status": "Open"},
        fields=["name", "date", FULFILLMENT_MARKER], limit=1) or []
    if existing:
        td = existing[0]
        patch = {}
        if not td.get(FULFILLMENT_MARKER):
            patch[FULFILLMENT_MARKER] = 1
        if date and _as_date(td.get("date")) != _as_date(date):
            # ToDo.date is a Date field; compare date-only so a repeat run is a
            # true no-op (write-idempotent), not a value-stable re-write.
            patch["date"] = date          # update a missing/old date to fulfillment_due_at
        if patch:
            frappe.db.set_value("ToDo", td["name"], patch, update_modified=False)
    else:
        _engine_ensure_todo(doctype, name, user, description, date, fulfillment=True)
    _engine_grant_read(doctype, name, user)
    _engine_maintain_assign(doctype, name, user, add=True)


def ensure_sole_todo(doctype, name, user, description=None, date=None):
    """Reconcile the FULFILLMENT ToDos of a business document to EXACTLY ONE, owned
    by `user` (Phase 1b.3.1b). Closes every OTHER Open fulfillment ToDo (scoped --
    unrelated tasks untouched) and guarantees `user` has one marked Open ToDo whose
    date == the governed fulfillment_due_at (created OR upgraded in place).

    Used by fulfillment CLAIM (the claimant, incl. a System Manager who was not in
    the fulfiller pool, ends with exactly one task) and by REASSIGNMENT (the old
    owner's task is closed, the new owner's ensured). Reuses the engine assignment
    service -- no direct ToDo inserts."""
    close_fulfillment_todos(doctype, name, keep_user=user)
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        _ensure_fulfillment_todo(doctype, name, user, description, date)
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
# Fulfillment ToDo lifecycle (Phase 1b.3.1b) -- generic across every
# fulfillment-capable form. reassign/cancel are ENGINE-INTERNAL (NOT whitelisted):
# no governed UI/use case exposes them yet; they are used by reconciliation and
# reserved for a future governed UI, with target-eligibility + explicit
# cancellation authority baked in.
# --------------------------------------------------------------------------- #
_FULFILLMENT_ACTIVE = ("Assigned", "In Progress")
_FULFILLMENT_TERMINAL = ("Completed", "Cancelled")
#: the six governed fulfillment-capable business DocTypes.
FULFILLMENT_DOCTYPES = ("EC AI Topup Request", "EC Asset Request", "EC Data Request",
                        "EC Document Request", "EC Resignation Request", "EC System Request")


def _fulfillment_snapshot(business_doctype, name):
    return frappe.db.get_value(
        business_doctype, name,
        ["fulfillment_status", "fulfillment_owner", "fulfillment_due_at",
         "approval_request", "requested_by"], as_dict=True) or {}


def _assert_owner_or_sm(actor, owner):
    if actor != owner and "System Manager" not in frappe.get_roles(actor):
        frappe.throw(_("Only the fulfillment owner or a System Manager may perform this action."))


def _assert_can_cancel(actor):
    """Cancellation authority is EXPLICIT (Phase 1b.3.1b review): System Manager
    only -- NOT automatically every fulfillment owner. Completing is the owner's
    action; cancelling an approved-and-assigned request is an admin action."""
    if "System Manager" not in frappe.get_roles(actor):
        frappe.throw(_("Only a System Manager may cancel an active fulfillment."))


def _resolve_fulfillers(approval_request, requested_by):
    """Eligible fulfillers for a request = the resolved Fulfiller participants of
    its Active approval process. Returns a set of user ids (may be empty)."""
    if not approval_request:
        return set()
    proc_name = frappe.db.get_value("EC Approval Request", approval_request, "approval_process")
    if not proc_name:
        return set()
    try:
        proc = frappe.get_doc("EC Approval Process", proc_name)
    except Exception:
        return set()
    parts = [p for p in proc.participants if p.participant_purpose == "Fulfiller"]
    return {u for u, _lbl in resolve_participants(parts, requested_by)}


def reassign_fulfillment(business_doctype, name, new_user, actor=None, description=None):
    """Governed fulfillment REASSIGNMENT (engine-internal). Reconciles ToDos: closes
    the OLD owner's fulfillment task and ensures the NEW owner has exactly one
    (ensure_sole_todo, scoped to fulfillment). Keeps the stage active and re-stamps
    fulfillment_due_at. Owner-or-SM gated. The TARGET must be an ENABLED, ELIGIBLE
    fulfiller (a resolved Fulfiller participant, or a System Manager). Audited;
    no direct ToDo inserts."""
    actor = actor or frappe.session.user
    snap = _fulfillment_snapshot(business_doctype, name)
    if snap.get("fulfillment_status") not in _FULFILLMENT_ACTIVE:
        frappe.throw(_("This request has no active fulfillment to reassign."))
    _assert_owner_or_sm(actor, snap.get("fulfillment_owner"))
    if not new_user or new_user == "Guest":
        frappe.throw(_("A valid new fulfiller is required."))
    if not frappe.db.get_value("User", new_user, "enabled"):
        frappe.throw(_("The new fulfiller must be an enabled user."))
    eligible = _resolve_fulfillers(snap.get("approval_request"), snap.get("requested_by"))
    if new_user not in eligible and "System Manager" not in frappe.get_roles(new_user):
        frappe.throw(_("The new fulfiller is not eligible to fulfill this request."))
    frappe.db.set_value(business_doctype, name,
                        {"fulfillment_owner": new_user, "fulfillment_status": "In Progress"})
    ensure_sole_todo(business_doctype, name, new_user, description, snap.get("fulfillment_due_at"))
    if snap.get("approval_request"):
        log_action(snap["approval_request"], "Assigned", actor,
                   comment=_("Fulfillment reassigned to {0}").format(new_user),
                   new_status="In Progress", related_user=new_user)
    notify([snap.get("requested_by"), new_user],
           _("Fulfillment reassigned to {0}: {1}").format(new_user, name), business_doctype, name)
    return {"owner": new_user, "reassigned": True}


def cancel_fulfillment(business_doctype, name, reason=None, actor=None):
    """Governed fulfillment CANCELLATION (engine-internal): mark
    fulfillment_status='Cancelled' and CLOSE ALL Open FULFILLMENT ToDos (scoped --
    unrelated ToDos untouched). Authority is EXPLICIT: System Manager only.
    Audited (action 'Cancelled'). Distinct from request-level cancel() (blocked
    once Approved)."""
    actor = actor or frappe.session.user
    snap = _fulfillment_snapshot(business_doctype, name)
    if snap.get("fulfillment_status") not in _FULFILLMENT_ACTIVE:
        frappe.throw(_("This request has no active fulfillment to cancel."))
    _assert_can_cancel(actor)
    frappe.db.set_value(business_doctype, name, {"fulfillment_status": "Cancelled"})
    close_fulfillment_todos(business_doctype, name)   # scoped: fulfillment tasks only
    if snap.get("approval_request"):
        log_action(snap["approval_request"], "Cancelled", actor,
                   comment=reason or _("Fulfillment cancelled"), new_status="Cancelled")
    notify([snap.get("requested_by"), snap.get("fulfillment_owner")],
           _("Fulfillment cancelled: {0}").format(name), business_doctype, name)
    return {"cancelled": True}


# ---- idempotent reconciliation (Phase 1b.3.1b review, blocker 2) -----------
def _open_todos_on(doctype, name):
    return frappe.get_all(
        "ToDo", filters={"reference_type": doctype, "reference_name": name, "status": "Open"},
        fields=["name", "allocated_to", "date", FULFILLMENT_MARKER]) or []


def _count_open_fulfillment(dts):
    n = 0
    for dt in dts:
        n += frappe.db.count("ToDo", {"reference_type": dt, "status": "Open",
                                      FULFILLMENT_MARKER: 1}) or 0
    return n


def reconcile_fulfillment_todos(doctypes=None):
    """Idempotent reconciliation of fulfillment ToDos for the six governed
    fulfillment DocTypes (blocker 2). Existing production records that were claimed
    before this batch never retrigger claim_fulfillment, so their governed ToDos
    may be missing/unmarked/mis-dated. Rules:
        Approved + active + owner    -> exactly one owner fulfillment ToDo
        Approved + active + no owner -> one pool ToDo per eligible fulfiller
        terminal fulfillment         -> no Open fulfillment ToDos
    First retroactively MARKS legacy fulfillment ToDos (only those allocated to a
    fulfillment participant, so UNRELATED ToDos are never touched), then applies
    the rules via the scoped engine helpers. Returns before/after Open-fulfillment
    counts. Safe to re-run (a second run makes no changes)."""
    dts = list(doctypes or FULFILLMENT_DOCTYPES)
    before = _count_open_fulfillment(dts)
    for dt in dts:
        recs = frappe.get_all(
            dt, filters={"fulfillment_status": ["in", list(_FULFILLMENT_ACTIVE) + list(_FULFILLMENT_TERMINAL)]},
            fields=["name", "fulfillment_status", "fulfillment_owner", "fulfillment_due_at",
                    "approval_request", "requested_by"], ignore_permissions=True) or []
        for r in recs:
            status = r.get("fulfillment_status")
            owner = (r.get("fulfillment_owner") or "").strip()
            due = r.get("fulfillment_due_at")
            fulfillers = _resolve_fulfillers(r.get("approval_request"), r.get("requested_by"))
            participants = set(fulfillers) | ({owner} if owner else set())
            # retroactively MARK legacy fulfillment ToDos (participant-allocated only)
            for td in _open_todos_on(dt, r["name"]):
                if td.get("allocated_to") in participants and not td.get(FULFILLMENT_MARKER):
                    frappe.db.set_value("ToDo", td["name"], {FULFILLMENT_MARKER: 1}, update_modified=False)
            if status in _FULFILLMENT_TERMINAL:
                close_fulfillment_todos(dt, r["name"])                     # terminal -> none
            elif owner:
                ensure_sole_todo(dt, r["name"], owner, _("Fulfillment"), due)   # exactly one owner
            else:
                for u in fulfillers:
                    _ensure_fulfillment_todo(dt, r["name"], u, _("Fulfillment"), due)  # one per fulfiller
                for td in _open_todos_on(dt, r["name"]):                   # drop marked non-fulfillers
                    if td.get(FULFILLMENT_MARKER) and td.get("allocated_to") not in fulfillers:
                        frappe.db.set_value("ToDo", td["name"], {"status": "Cancelled"},
                                            update_modified=False)
                        _engine_maintain_assign(dt, r["name"], td.get("allocated_to"), add=False)
    after = _count_open_fulfillment(dts)
    return {"before": before, "after": after, "doctypes": dts}


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
    from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
    from ecentric_workspace.approval_center.shared.workflow import holidays as hol
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


def _no_approver_message(lvl, requester):
    """Actionable fail-closed message. The old text ("No approver resolved for level N") told
    the user nothing they could act on; in practice the cause is almost always one of two data
    gaps, so name them explicitly and say which department is involved. Diagnostic only - it
    changes no behaviour and leaks no amounts/PII beyond the department name the requester
    already belongs to. Generic: reads config/HR data, no hardcoded identities."""
    src = {p.source_type for p in (lvl.participants or [])
           if p.participant_purpose == "Approver"}
    emp = _emp_user(requester) or {}
    dept = None
    try:
        dept = frappe.db.get_value("Department", {"manager_email": requester, "disabled": 0}, "name")
    except Exception:
        dept = None
    dept = dept or emp.get("department")
    hints = []
    if "Department Manager" in src:
        # Duong duoc chot 28/08: khong tra ra truong phong thi CHAN viec gui, va noi ro
        # phai lam gi - hoac chon nguoi duyet Cap 1 ngay tren phieu, hoac de HR gan truong
        # phong cho phong do. Khong tu mo cho ca nhom truong phong.
        if dept:
            hints.append(_("department '{0}' has no valid manager (Department.manager_email must "
                           "be an active user)").format(dept))
        else:
            hints.append(_("the requester is not linked to any department"))
    if "Requester Manager" in src and not emp.get("reports_to"):
        hints.append(_("the requester's Employee record has no 'Reports To'"))
    detail = ("; ".join(hints)) if hints else _("no participant source resolved a user")
    return _("Cannot submit: no approver could be determined for level {0} ({1}). Cause: {2}. "
             "Ask HR/admin to fix the data above, then submit again."
             ).format(lvl.level_no, lvl.level_name, detail)


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
            frappe.throw(_no_approver_message(lvl, requester))
        for user, label in approvers:
            frappe.get_doc({
                "doctype": "EC Approval Request Approver", "approval_request": req.name,
                "request_level": rl.name, "level_no": lvl.level_no, "approver": user,
                "source": label, "status": "Pending",
            }).insert(ignore_permissions=True)


def is_active_process_fulfiller(approval_type, user=None):
    """True if `user` is a Fulfiller participant on the current Active/Draft process for
    `approval_type`. Dynamic (reads live config), so a newly-added fulfiller can claim from the
    queue right away - keeps claim permission consistent with queue visibility. Read-only; no
    workflow/state change."""
    user = user or frappe.session.user
    for name in frappe.get_all("EC Approval Process",
                               filters={"approval_type": approval_type, "status": ["in", ["Active", "Draft"]]},
                               pluck="name"):
        if frappe.db.exists("EC Approval Participant",
                            {"parent": name, "parenttype": "EC Approval Process",
                             "participant_purpose": "Fulfiller", "user": user}):
            return True
    return False


def submit(reference_doctype, reference_name, approval_type, requester, process_code=None,
           activate_first_level=True, skip_level_nos=None, skip_reason=None):
    """skip_level_nos: level_no bị loại khỏi snapshot của RIÊNG request này (tuỳ điều kiện
    nghiệp vụ do service của form quyết định — engine giữ trung tính, chỉ nhận danh sách).
    Chỉ được bỏ cấp KHÔNG mandatory; việc bỏ được ghi audit kèm skip_reason."""
    process = resolve_process(approval_type, process_code)
    levels = resolve_levels(process.name)
    if not levels:
        frappe.throw(_("Process {0} has no levels.").format(process.name))
    skipped = []
    if skip_level_nos:
        wanted = {int(n) for n in skip_level_nos}
        keep = []
        for lvl in levels:
            if lvl.level_no in wanted:
                if lvl.mandatory:
                    frappe.throw(_("Level {0} ({1}) is mandatory and cannot be skipped.")
                                 .format(lvl.level_no, lvl.level_name))
                skipped.append(lvl)
            else:
                keep.append(lvl)
        levels = keep
        if not levels:
            frappe.throw(_("Process {0} has no levels left after skipping.").format(process.name))
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
    for lvl in skipped:
        log_action(req.name, "Skipped", requester,
                   comment=(skip_reason or "Level skipped by business condition")
                           + " (level %s - %s)" % (lvl.level_no, lvl.level_name))
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
    notify(approvers, _("C\u1ea7n duy\u1ec7t: {0}").format(request_label(req.reference_doctype, req.reference_name, req.approval_type)), req.reference_doctype, req.reference_name)
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
    from ecentric_workspace.platform.esign import guard as esign_guard
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


def _esign_on_reopen(request_name):
    """Declared cross-module call into platform.esign. Returns a plain dict.

    Only a MISSING module is tolerated. A real failure must propagate: a resubmit that
    silently continues against a stale, frozen signing package is exactly the defect this
    call exists to prevent (documents supplemented after a send-back never entered the
    package, so later levels signed the old set - observed 2026-08-27).
    """
    try:
        from ecentric_workspace.platform.esign import lifecycle as esign_lifecycle
    except ImportError:
        return {"revised": False, "new_package": None, "force_restart": False}
    return esign_lifecycle.on_request_reopened(request_name)


def resubmit(request_name, actor=None, restart=False):
    req = frappe.get_doc("EC Approval Request", request_name)
    if req.approval_status not in ("Information Required",) and not restart:
        frappe.throw(_("Only an Information Required request can be resubmitted."))
    # Revise the signing package BEFORE the levels are reset: whether the approval resumes
    # mid-chain or starts over depends on whether signatures were already collected.
    esign = _esign_on_reopen(request_name)
    if esign.get("force_restart"):
        restart = True
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
    note = None
    if esign.get("force_restart"):
        note = _("Bắt đầu lại từ cấp 1: tài liệu ký đã đổi nên các chữ ký số đã thu thập "
                 "không còn chứng thực cho bộ tài liệu hiện tại.")
    elif esign.get("revised"):
        note = _("Đã tạo phiên bản mới của gói ký để nhận chứng từ bổ sung.")
    elif restart:
        note = _("Restarted from level 1 (material change)")
    log_action(request_name, "Restarted" if restart else "Resubmitted", actor or req.requested_by,
               resume, comment=note, new_status="Pending")
    _activate_level(frappe.get_doc("EC Approval Request", request_name), resume)
    return {"esign": esign}


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
    "EC AI Topup Request": "ecentric_workspace.approval_center.features.ai_topup.application.service.on_final_approval",
    "EC Data Request": "ecentric_workspace.approval_center.features.data_request.application.service.on_final_approval",
    "EC Document Request": "ecentric_workspace.approval_center.features.document_request.application.service.on_final_approval",
    "EC System Request": "ecentric_workspace.approval_center.features.system_request.application.service.on_final_approval",
    "EC Asset Request": "ecentric_workspace.approval_center.features.asset_request.application.service.on_final_approval",
    "EC Resignation Request": "ecentric_workspace.approval_center.features.resignation.application.service.on_final_approval",
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
