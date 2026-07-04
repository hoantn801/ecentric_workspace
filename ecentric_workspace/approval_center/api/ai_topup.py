# Copyright (c) 2026, eCentric and contributors
"""B3.1 permission-safe READ API layer for the AI Topup frontend.

Thin read wrappers over the deployed B1/B2 engine (no orchestration duplicated).
Every list/detail enforces server-side scope; capability flags tell the UI which
actions to show, but the backend re-validates every write elsewhere.
"""
import frappe
from frappe import _

BIZ = "EC AI Topup Request"
APPROVAL_TYPE = "AI_TOPUP"
OPEN = ("Pending", "Information Required")
MAX_PAGE = 50
_EDITABLE_DRAFT = ("request_title", "account_mode", "ai_account", "ai_tool", "account_email", "account_manager",
                   "current_plan", "proposed_account_email", "proposed_account_manager", "proposed_plan",
                   "request_type", "requested_plan", "requested_amount", "currency", "needed_by",
                   "purpose", "requester_note", "subscription_start_date", "subscription_end_date",
                   "billing_cycle", "auto_renewal_expected", "subscription_start_date")
_STATUS_LABEL = {  # engine + fulfillment -> user-facing Vietnamese
    "Draft": "Nháp", "Pending": "Đang phê duyệt", "Information Required": "Cần bổ sung thông tin",
    "Approved": "Đã duyệt", "Rejected": "Bị từ chối", "Cancelled": "Đã hủy",
}


# --------------------------------------------------------------------------- #
def _sm():
    return "System Manager" in frappe.get_roles(frappe.session.user)


def _employee_ctx(user=None):
    user = user or frappe.session.user
    emp = frappe.db.get_value("Employee", {"user_id": user},
                              ["name", "employee_name", "department", "company", "reports_to"], as_dict=True)
    manager_user = None
    if emp and emp.reports_to:
        manager_user = frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return {
        "user": user,
        "employee": emp.name if emp else None,
        "employee_name": emp.employee_name if emp else None,
        "department": emp.department if emp else None,
        "company": emp.company if emp else None,
        "manager_user": manager_user,
        "manager_resolvable": bool(manager_user),
    }


def _is_fulfiller(user=None):
    user = user or frappe.session.user
    if _sm():
        return True
    # configured Fulfiller on the active AI_TOPUP process, or has an open fulfillment ToDo
    procs = frappe.get_all("EC Approval Process",
                           filters={"approval_type": APPROVAL_TYPE, "status": "Active"}, pluck="name")
    for p in procs:
        if frappe.db.exists("EC Approval Participant",
                            {"parent": p, "parenttype": "EC Approval Process",
                             "participant_purpose": "Fulfiller", "user": user}):
            return True
    return bool(frappe.db.exists("ToDo", {"reference_type": BIZ, "allocated_to": user, "status": "Open"}))


def _has_any_approver_row(user=None):
    user = user or frappe.session.user
    return bool(frappe.db.exists("EC Approval Request Approver", {"approver": user}))


def _req_of(biz_name):
    ar = frappe.db.get_value(BIZ, biz_name, "approval_request")
    return frappe.get_doc("EC Approval Request", ar) if ar else None


def _can_view(user, biz, req):
    if _sm() or biz.requested_by == user:
        return True
    if req and frappe.db.exists("EC Approval Request Approver",
                                {"approval_request": req.name, "approver": user}):
        return True
    if biz.fulfillment_owner == user or _is_fulfiller(user):
        return True
    return False


def _pending_row(req, user):
    if not req or req.approval_status not in OPEN:
        return None
    return frappe.db.exists("EC Approval Request Approver",
                            {"approval_request": req.name, "level_no": req.current_level,
                             "approver": user, "status": "Pending"})


def _has_decision(req):
    if not req:
        return False
    return bool(frappe.db.exists("EC Approval Action",
                {"approval_request": req.name,
                 "action": ["in", ["Approved", "Rejected", "Information Requested"]]}))


def _capabilities(user, biz, req):
    is_requester = biz.requested_by == user
    open_ = req and req.approval_status in OPEN
    can_act = bool(_pending_row(req, user))
    can_adjust = False
    if can_act:
        can_adjust = bool(frappe.db.get_value("EC Approval Request Level",
                          {"approval_request": req.name, "level_no": req.current_level},
                          "allows_amount_adjustment"))
    cancel_requester = is_requester and (req is None or (req.approval_status == "Pending" and not _has_decision(req)))
    cancel_admin = (_sm()) and open_
    return {
        "can_edit": is_requester and (req is None or req.approval_status == "Information Required"),
        "can_submit": is_requester and req is None,
        "can_resubmit": is_requester and bool(req) and req.approval_status == "Information Required",
        "can_cancel": bool(cancel_requester or cancel_admin),
        "can_approve": can_act,
        "can_reject": can_act,
        "can_request_information": can_act,
        "can_adjust_approved_amount": can_adjust,
        "can_claim": _is_fulfiller(user) and biz.fulfillment_status == "Assigned",
        "can_complete": (biz.fulfillment_owner == user or _sm())
                        and biz.fulfillment_status in ("Assigned", "In Progress"),
        "can_view_fulfillment": _is_fulfiller(user) or is_requester or _sm(),
    }


# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_bootstrap():
    user = frappe.session.user
    ctx = _employee_ctx(user)
    return {
        "context": ctx,
        "is_system_manager": _sm(),
        "tabs": {
            "create": True, "my_requests": True,
            "my_approvals": _has_any_approver_row(user) or _sm(),
            "fulfillment": _is_fulfiller(user),
        },
        "form_options": get_form_options(),
    }


@frappe.whitelist()
def get_form_options():
    return {
        "ai_tools": frappe.get_all("EC AI Tool", filters={"is_active": 1},
                                   fields=["name as value", "tool_name as label", "default_currency"]),
        "currencies": frappe.get_all("Currency", filters={"enabled": 1}, pluck="name"),
        "account_modes": ["Existing Account", "New Account"],
        "request_types": ["New Subscription", "Renewal", "Top-up", "Upgrade"],
        "billing_cycles": ["Monthly", "Quarterly", "Semi-annual", "Annual", "One-time", "Custom"],
    }


@frappe.whitelist()
def search_ai_accounts(query=None, ai_tool=None):
    filters = {"status": "Active"}
    if ai_tool:
        filters["ai_tool"] = ai_tool
    or_filters = None
    if query:
        or_filters = [["account_email", "like", "%" + query + "%"],
                      ["account_name", "like", "%" + query + "%"]]
    return frappe.get_all("EC AI Account", filters=filters, or_filters=or_filters,
                          fields=["name", "ai_tool", "account_email", "account_name",
                                  "account_manager", "current_plan",
                                  "subscription_start_date", "subscription_end_date"],
                          limit_page_length=20, order_by="account_email asc")


@frappe.whitelist()
def search_active_users(query=None):
    # Only enabled System Users; Administrator hidden unless caller is System Manager.
    filters = {"enabled": 1, "user_type": "System User"}
    or_filters = None
    if query:
        or_filters = [["full_name", "like", "%" + query + "%"], ["name", "like", "%" + query + "%"]]
    rows = frappe.get_all("User", filters=filters, or_filters=or_filters,
                          fields=["name", "full_name"], limit_page_length=MAX_PAGE,
                          order_by="full_name asc")
    if not _sm():
        rows = [r for r in rows if r.name != "Administrator"]
    # minimal, fixed shape: email(name)/full_name only
    return [{"value": r.name, "email": r.name, "label": r.full_name or r.name} for r in rows[:20]]


def _scope_status(biz, req):
    if not req:
        return "Draft"
    if req.approval_status == "Approved":
        return biz.fulfillment_status or "Approved"
    return req.approval_status


@frappe.whitelist()
def list_my_requests(filters=None, start=0, page_length=20):
    user = frappe.session.user
    flt = {"requested_by": user}          # server-side scope
    f = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    for k in ("ai_tool", "request_type"):
        if f.get(k):
            flt[k] = f[k]
    if f.get("from_date") and f.get("to_date"):
        flt["creation"] = ["between", [f["from_date"], f["to_date"]]]
    overdue_names = _overdue_request_names() if f.get("overdue_only") else None
    if overdue_names is not None:
        flt["approval_request"] = ["in", overdue_names or ["__none__"]]
    page_length = min(int(page_length or 20), MAX_PAGE)  # enforce max page size
    total = frappe.db.count(BIZ, flt)
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "request_title", "ai_tool", "account_mode", "account_email",
                                  "proposed_account_email", "request_type", "requested_amount",
                                  "currency", "fulfillment_status", "approval_request", "creation", "modified"],
                          limit_start=int(start), limit_page_length=page_length,
                          order_by="modified desc")  # fixed server-side sort (no client sort injection)
    for r in rows:
        ar = r.approval_request and frappe.db.get_value(
            "EC Approval Request", r.approval_request, ["approval_status", "current_level"], as_dict=True)
        r["approval_status"] = ar.approval_status if ar else "Draft"
        r["current_level"] = ar.current_level if ar else 0
    return {"rows": rows, "total": total}


@frappe.whitelist()
def list_my_approvals(section="pending"):
    user = frappe.session.user
    status = ["Pending"] if section == "pending" else ["Approved", "Rejected", "Information Requested", "Skipped"]
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approver": user, "status": ["in", status]},
                          fields=["approval_request", "level_no", "status", "decided_at"],
                          order_by="modified desc", limit_page_length=200)
    out = []
    for r in rows:
        req = frappe.db.get_value("EC Approval Request", r.approval_request,
                                  ["reference_name", "approval_status", "current_level",
                                   "requested_by", "submitted_at"], as_dict=True)
        if not req:
            continue
        if section == "pending" and (req.approval_status not in OPEN or req.current_level != r.level_no):
            continue  # only actionable current-level rows
        biz = frappe.db.get_value(BIZ, req.reference_name,
                                  ["name", "request_title", "ai_tool", "account_mode", "account_email",
                                   "proposed_account_email", "requested_amount", "department"], as_dict=True)
        if biz:
            biz.update({"approval_request": r.approval_request, "level_no": r.level_no,
                        "approval_status": req.approval_status, "requested_by": req.requested_by,
                        "my_status": r.status})
            out.append(biz)
    return {"rows": out}


@frappe.whitelist()
def list_fulfillment_queue(section="unclaimed"):
    user = frappe.session.user
    if not _is_fulfiller(user):
        frappe.throw(_("You are not an eligible fulfiller."), frappe.PermissionError)
    flt = {}
    if section == "unclaimed":
        flt = {"fulfillment_status": "Assigned"}
    elif section == "mine":
        flt = {"fulfillment_owner": user, "fulfillment_status": ["in", ["Assigned", "In Progress"]]}
    elif section == "others" and _sm():
        flt = {"fulfillment_status": "In Progress", "fulfillment_owner": ["!=", user]}
    else:
        return {"rows": []}
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "requested_by", "ai_tool", "account_email", "approved_amount",
                                  "subscription_start_date", "subscription_end_date", "fulfillment_status",
                                  "fulfillment_owner", "fulfillment_due_at"],
                          order_by="modified desc", limit_page_length=100)
    return {"rows": rows}


def _process_preview(approval_type):
    """Configured approval levels (level_no, level_name) for the active AI_TOPUP process,
    for the Draft/pre-submit stepper preview. Falls back to a Draft process if none Active.
    No approvers are returned here (config only, not runtime)."""
    proc = frappe.get_all("EC Approval Process",
                          filters={"approval_type": approval_type, "status": "Active"}, pluck="name")
    if not proc:
        proc = frappe.get_all("EC Approval Process",
                              filters={"approval_type": approval_type, "status": "Draft"},
                              order_by="creation desc", pluck="name")
    if not proc:
        return []
    return frappe.get_all("EC Approval Level", filters={"approval_process": proc[0]},
                          fields=["level_no", "level_name"], order_by="level_no asc")


@frappe.whitelist()
def get_request_detail(name):
    user = frappe.session.user
    biz = frappe.get_doc(BIZ, name)
    req = _req_of(name)
    if not _can_view(user, biz, req):
        frappe.throw(_("You do not have access to this request."), frappe.PermissionError)
    levels, approvers, timeline, sla = [], [], [], {}
    if req:
        levels = frappe.get_all("EC Approval Request Level", filters={"approval_request": req.name},
                                fields=["level_no", "level_name", "approval_mode", "minimum_approvals",
                                        "mandatory", "level_status", "activated_at", "completed_at",
                                        "due_at", "sla_calendar", "sla_holiday_list"], order_by="level_no asc")
        approvers = frappe.get_all("EC Approval Request Approver", filters={"approval_request": req.name},
                                   fields=["level_no", "approver", "source", "status", "decided_at", "comment"],
                                   order_by="level_no asc")
        timeline = frappe.get_all("EC Approval Action", filters={"approval_request": req.name},
                                  fields=["seq", "level_no", "level_name", "actor", "action", "comment",
                                          "action_time", "previous_status", "new_status", "related_user"],
                                  order_by="seq asc")
    attachments = frappe.get_all("File", filters={"attached_to_doctype": BIZ, "attached_to_name": name},
                                 fields=["file_name", "file_url", "is_private", "owner", "creation"])
    ff = {"status": biz.fulfillment_status, "owner": biz.fulfillment_owner,
          "due_at": biz.fulfillment_due_at, "completed_by": biz.completed_by, "completed_at": biz.completed_at,
          "eligible_fulfillers": [], "ai_account": None}
    if req and biz.fulfillment_status == "Assigned":
        try:
            from ecentric_workspace.approval_center.engine import service as _eng
            proc = frappe.get_doc("EC Approval Process", req.approval_process)
            ff["eligible_fulfillers"] = [u for u, _l in _eng.resolve_participants(
                [p for p in proc.participants if p.participant_purpose == "Fulfiller"], biz.requested_by)]
        except Exception:
            pass
    if biz.actual_ai_account:
        ff["ai_account"] = frappe.db.get_value("EC AI Account", biz.actual_ai_account,
            ["name", "account_email", "account_manager", "current_plan", "subscription_start_date",
             "subscription_end_date", "last_topup_at"], as_dict=True)
    return {
        "business": biz.as_dict(),
        "approval": {
            "name": req.name if req else None,
            "approval_status": req.approval_status if req else "Draft",
            "current_level": req.current_level if req else 0,
            "information_requested_from_level": req.information_requested_from_level if req else None,
            "status_label": _STATUS_LABEL.get(req.approval_status if req else "Draft"),
        },
        "levels": levels,
        "approvers": approvers,
        "fulfillment": ff,
        "attachments": attachments,
        "timeline": timeline,
        "process_preview": ([] if req else _process_preview(biz.approval_type or APPROVAL_TYPE)),
        "capabilities": _capabilities(user, biz, req),
    }


def _overdue_request_names():
    from frappe.utils import now_datetime
    rows = frappe.get_all("EC Approval Request Level",
                          filters={"level_status": "In Progress", "due_at": ["<", now_datetime()]},
                          fields=["approval_request"], distinct=True)
    return list({r.approval_request for r in rows})


@frappe.whitelist(methods=["POST"])
def save_draft(name=None, payload=None):
    """Create/update an AI Topup draft (owner or SM). Only editable business
    fields are accepted; controller validates. No orchestration here."""
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    if name:
        doc = frappe.get_doc(BIZ, name)
        req = _req_of(name)
        if doc.requested_by != user and not _sm():
            frappe.throw(_("You can only edit your own request."), frappe.PermissionError)
        if req and req.approval_status not in ("Information Required",):
            frappe.throw(_("Only a Draft or an Information-Required request can be edited."))
    else:
        doc = frappe.new_doc(BIZ)
        doc.requested_by = user
    for fld in _EDITABLE_DRAFT:
        if fld in data:
            doc.set(fld, data.get(fld))
    ctx = _employee_ctx(doc.requested_by)
    doc.employee = ctx["employee"]
    doc.department = doc.department or ctx["department"]
    doc.company = doc.company or ctx["company"]
    doc.save(ignore_permissions=True)   # EC AI Topup Request controller enforces the rules
    return {"name": doc.name, "capabilities": _capabilities(user, doc, _req_of(doc.name))}


@frappe.whitelist(methods=["POST"])
def submit_request(name):
    """Thin wrapper over the deployed B1 submit service (guards own-only,
    resolves manager, builds the frozen snapshot, activates level 1)."""
    from ecentric_workspace.approval_center.ai_topup import service as svc
    approval_request = svc.submit(name)
    return {"approval_request": approval_request, "detail": get_request_detail(name)}


# --------------------------------------------------------------------------- #
# B3.3 write wrappers - thin; call B1/B2 services (no orchestration duplicated).
# --------------------------------------------------------------------------- #
def _resolve_req(name):
    doc = frappe.get_doc(BIZ, name)
    if not doc.approval_request:
        frappe.throw(_("This request has not been submitted."))
    return doc, doc.approval_request


@frappe.whitelist(methods=["POST"])
def approve(name, comment=None, approved_amount=None):
    from ecentric_workspace.approval_center.engine import service as engine
    from ecentric_workspace.approval_center.ai_topup import service as svc
    doc, req = _resolve_req(name)
    if approved_amount not in (None, ""):
        # Finance amount adjustment -> dedicated service (logs Amount Adjusted,
        # enforces mandatory comment when != requested); it then calls engine.approve.
        svc.finance_approve(name, approved_amount=approved_amount, comment=comment)
    else:
        engine.approve(req, comment=comment)   # engine re-checks pending approver + level + duplicate
    return {"detail": get_request_detail(name)}


@frappe.whitelist(methods=["POST"])
def reject(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    doc, req = _resolve_req(name)
    engine.reject(req, comment=comment)        # engine enforces mandatory reason + terminal
    return {"detail": get_request_detail(name)}


@frappe.whitelist(methods=["POST"])
def request_information(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    doc, req = _resolve_req(name)
    engine.request_information(req, comment=comment)   # engine enforces mandatory comment
    return {"detail": get_request_detail(name)}


@frappe.whitelist(methods=["POST"])
def resubmit(name, payload=None):
    from ecentric_workspace.approval_center.ai_topup import service as svc
    if payload:
        save_draft(name=name, payload=payload)   # owner guard + controller validation
    res = svc.resubmit(name)                     # material_signature comparison is authoritative
    return {"restarted": bool(res.get("restarted")), "detail": get_request_detail(name)}


@frappe.whitelist(methods=["POST"])
def cancel(name, reason=None):
    from ecentric_workspace.approval_center.engine import service as engine
    user = frappe.session.user
    doc = frappe.get_doc(BIZ, name)
    req = _req_of(name)
    if not _capabilities(user, doc, req)["can_cancel"]:
        frappe.throw(_("You are not allowed to cancel this request."), frappe.PermissionError)
    if req:
        engine.cancel(req, reason=reason)        # engine enforces mandatory reason + audit
        return {"detail": get_request_detail(name)}
    frappe.delete_doc(BIZ, name, ignore_permissions=True)   # discard a never-submitted draft
    return {"deleted": True}


_COMPLETION_FIELDS = ("actual_ai_account", "actual_account_email", "confirmed_account_manager",
                      "actual_plan", "actual_amount", "actual_currency", "topup_datetime",
                      "transaction_reference", "payment_proof", "invoice_status", "invoice_receipt",
                      "no_invoice_reason", "operation_note")


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name):
    """Thin wrapper over the deployed atomic claim service (B1). Backend
    revalidates eligibility + concurrency; no claim logic duplicated here."""
    from ecentric_workspace.approval_center.ai_topup import service as svc
    svc.claim_fulfillment(name)
    return {"detail": get_request_detail(name)}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, payload=None):
    """Apply completion fields (owner/SM only) then call the deployed completion
    service, which validates evidence (payment proof + invoice conditional) and
    upserts EC AI Account. No fulfillment rules duplicated; no direct account
    mutation from the API."""
    from ecentric_workspace.approval_center.ai_topup import service as svc
    user = frappe.session.user
    doc = frappe.get_doc(BIZ, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Only the claimed owner or a System Manager may complete this request."),
                     frappe.PermissionError)
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    for fld in _COMPLETION_FIELDS:
        if fld in data:
            doc.set(fld, data.get(fld))
    doc.save(ignore_permissions=True)          # still In Progress; controller validates non-completion rules
    svc.complete_fulfillment(name, user=user)  # sets Completed -> evidence validation + AI Account upsert
    return {"detail": get_request_detail(name)}
