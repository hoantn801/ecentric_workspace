# Copyright (c) 2026, eCentric and contributors
"""Permission-safe read + write API for Asset Request (form #7). Mirrors AI Topup
conventions WITH a post-approval fulfillment queue. Backend is authoritative;
capability flags are advisory (writes re-validate in the engine/service).
Friendly Vietnamese errors only; raw Frappe share messages suppressed on write."""
import frappe
from frappe import _

BIZ = "EC Asset Request"
APPROVAL_TYPE = "ASSET_REQUEST"
MAX_PAGE = 50
OPEN = ("Pending", "Information Required")
TERMINAL = ("Approved", "Rejected", "Cancelled")

_EDITABLE_DRAFT = ("request_title", "request_type", "asset_type", "asset_type_other", "purpose_of_request",
                   "purpose_other", "quantity", "specifications", "justification", "requested_needed_date",
                   "request_attachment", "department", "company")

_STATUS_LABEL = {"Draft": "Nhap", "Pending": "Dang phe duyet", "Information Required": "Can bo sung",
                 "Approved": "Da duyet", "Rejected": "Bi tu choi", "Cancelled": "Da huy",
                 "Assigned": "Cho Operation xu ly", "In Progress": "Operation dang xu ly", "Completed": "Hoan tat"}


def _sm():
    return "System Manager" in frappe.get_roles(frappe.session.user)


def _employee_ctx(user=None):
    user = user or frappe.session.user
    emp = frappe.db.get_value("Employee", {"user_id": user},
                              ["name", "employee_name", "department", "company", "reports_to"], as_dict=True)
    manager_user = None
    if emp and emp.reports_to:
        manager_user = frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return {"user": user, "employee": emp.name if emp else None,
            "employee_name": emp.employee_name if emp else None,
            "department": emp.department if emp else None, "company": emp.company if emp else None,
            "manager_user": manager_user, "manager_resolvable": bool(manager_user)}


def _is_fulfiller(user=None):
    user = user or frappe.session.user
    if _sm():
        return True
    proc = frappe.get_all("EC Approval Process",
                          filters={"approval_type": APPROVAL_TYPE, "status": ["in", ["Active", "Draft"]]},
                          order_by="status asc", pluck="name")
    for p in proc:
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
    if not ar:
        return None
    return frappe.db.get_value("EC Approval Request", ar,
                               ["name", "approval_status", "current_level",
                                "information_requested_from_level", "requested_by"], as_dict=True)


def _can_view(user, biz, req):
    if biz.requested_by == user or _sm():
        return True
    if biz.fulfillment_owner == user or _is_fulfiller(user):
        return True
    return bool(req and frappe.db.exists("EC Approval Request Approver",
                                         {"approval_request": req.name, "approver": user}))


def _pending_row(req, user):
    if not req or req.approval_status not in OPEN or not req.current_level:
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
    cancel_requester = is_requester and (req is None or (req.approval_status == "Pending" and not _has_decision(req)))
    cancel_admin = _sm() and open_
    can_admin_approve = False
    if _sm() and req and req.approval_status == "Pending" and req.current_level:
        cl = frappe.db.get_value("EC Approval Request Level",
                                 {"approval_request": req.name, "level_no": req.current_level}, "level_status")
        can_admin_approve = (cl == "In Progress")
    return {
        "can_edit": is_requester and (req is None or req.approval_status == "Information Required"),
        "can_submit": is_requester and req is None,
        "can_resubmit": is_requester and bool(req) and req.approval_status == "Information Required",
        "can_cancel": bool(cancel_requester or cancel_admin),
        "can_approve": can_act, "can_reject": can_act, "can_request_information": can_act,
        "can_admin_approve_current_level": can_admin_approve,
        "can_claim": _is_fulfiller(user) and biz.fulfillment_status == "Assigned",
        "can_complete": (biz.fulfillment_owner == user or _sm())
                        and biz.fulfillment_status in ("Assigned", "In Progress"),
        "can_view_fulfillment": _is_fulfiller(user) or is_requester or _sm(),
    }


def _process_preview(approval_type):
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


def _active_level_count():
    return len(_process_preview(APPROVAL_TYPE))


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_bootstrap():
    user = frappe.session.user
    return {"context": _employee_ctx(user), "is_system_manager": _sm(),
            "tabs": {"create": True, "my_requests": True,
                     "my_approvals": _has_any_approver_row(user) or _sm(),
                     "fulfillment": _is_fulfiller(user)},
            "form_options": get_form_options()}


@frappe.whitelist()
def get_form_options():
    return {
        "request_types": ["Request new asset", "Return old asset"],
        "asset_types": ["Laptop", "Desktop computer", "Monitor", "Mobile device", "Printer", "RAM", "Other"],
        "purposes": ["New employee", "Replacement of damaged or obsolete asset",
                     "Additional asset for current use", "Offboarding", "Laptop Allowance", "Other"],
    }


@frappe.whitelist()
def list_my_requests(filters=None, start=0, page_length=20):
    user = frappe.session.user
    flt = {"requested_by": user}
    f = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if f.get("request_type"):
        flt["request_type"] = f["request_type"]
    if f.get("from_date") and f.get("to_date"):
        flt["creation"] = ["between", [f["from_date"], f["to_date"]]]
    page_length = min(int(page_length or 20), MAX_PAGE)
    total = frappe.db.count(BIZ, flt)
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "request_title", "request_type", "asset_type", "quantity",
                                  "requested_needed_date", "operation_expected_completion_date",
                                  "fulfillment_status", "approval_request", "creation", "modified"],
                          limit_start=int(start), limit_page_length=page_length, order_by="modified desc")
    alc = None
    for r in rows:
        ar = r.approval_request and frappe.db.get_value(
            "EC Approval Request", r.approval_request, ["approval_status", "current_level"], as_dict=True)
        r["approval_status"] = ar.approval_status if ar else "Draft"
        r["current_level"] = ar.current_level if ar else 0
        if r.approval_request:
            r["total_levels"] = frappe.db.count("EC Approval Request Level",
                                                {"approval_request": r.approval_request})
            r["current_level_name"] = (frappe.db.get_value(
                "EC Approval Request Level",
                {"approval_request": r.approval_request, "level_no": r["current_level"]}, "level_name")
                if r["current_level"] else None)
        else:
            if alc is None:
                alc = _active_level_count()
            r["total_levels"] = alc
            r["current_level_name"] = None
    return {"rows": rows, "total": total}


@frappe.whitelist()
def list_need_my_approval(section="pending"):
    user = frappe.session.user
    status = ["Pending"] if section == "pending" else ["Approved", "Rejected", "Information Requested", "Skipped"]
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approver": user, "status": ["in", status]},
                          fields=["approval_request", "level_no", "status", "decided_at"],
                          order_by="modified desc", limit_page_length=200)
    out = []
    for r in rows:
        req = frappe.db.get_value("EC Approval Request", r.approval_request,
                                  ["reference_name", "reference_doctype", "approval_status",
                                   "current_level", "requested_by"], as_dict=True)
        if not req or req.reference_doctype != BIZ:
            continue
        if section == "pending" and (req.approval_status not in OPEN or req.current_level != r.level_no):
            continue
        biz = frappe.db.get_value(BIZ, req.reference_name,
                                  ["name", "request_title", "request_type", "asset_type", "quantity",
                                   "requested_needed_date", "department"], as_dict=True)
        if biz:
            biz.update({"approval_request": r.approval_request, "level_no": r.level_no,
                        "approval_status": req.approval_status, "requested_by": req.requested_by,
                        "my_status": r.status,
                        "total_levels": frappe.db.count("EC Approval Request Level",
                                                        {"approval_request": r.approval_request}),
                        "level_name": frappe.db.get_value("EC Approval Request Level",
                                        {"approval_request": r.approval_request, "level_no": r.level_no},
                                        "level_name")})
            out.append(biz)
    return {"rows": out}


list_my_approvals = list_need_my_approval


@frappe.whitelist()
def list_fulfillment_queue(section="unclaimed"):
    user = frappe.session.user
    if not _is_fulfiller(user):
        return {"rows": []}
    if section == "unclaimed":
        flt = {"fulfillment_status": "Assigned"}
    elif section == "mine":
        flt = {"fulfillment_owner": user, "fulfillment_status": ["in", ["Assigned", "In Progress"]]}
    else:
        flt = {"fulfillment_status": "In Progress", "fulfillment_owner": ["!=", user]}
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "request_title", "requested_by", "request_type", "asset_type",
                                  "quantity", "requested_needed_date", "operation_expected_completion_date",
                                  "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"],
                          order_by="modified asc", limit_page_length=200)
    return {"rows": rows}


@frappe.whitelist()
def get_detail(name):
    user = frappe.session.user
    biz = frappe.get_doc(BIZ, name)
    req = _req_of(name)
    if not _can_view(user, biz, req):
        frappe.throw(_("Ban khong co quyen xem yeu cau nay."), frappe.PermissionError)
    levels, approvers, timeline = [], [], []
    if req:
        levels = frappe.get_all("EC Approval Request Level", filters={"approval_request": req.name},
                                fields=["level_no", "level_name", "approval_mode", "minimum_approvals",
                                        "mandatory", "level_status", "activated_at", "completed_at", "due_at"],
                                order_by="level_no asc")
        approvers = frappe.get_all("EC Approval Request Approver", filters={"approval_request": req.name},
                                   fields=["level_no", "approver", "source", "status", "decided_at", "comment"],
                                   order_by="level_no asc")
        timeline = frappe.get_all("EC Approval Action", filters={"approval_request": req.name},
                                  fields=["seq", "request_level", "actor", "action", "comment",
                                          "action_time", "previous_status", "new_status"], order_by="seq asc")
        lvl_by_name = {r.name: r for r in frappe.get_all(
            "EC Approval Request Level", filters={"approval_request": req.name},
            fields=["name", "level_no", "level_name"])}
        for a in timeline:
            lv = lvl_by_name.get(a.get("request_level"))
            if lv:
                a["level_no"] = lv.level_no
                a["level_name"] = lv.level_name
    attachments = frappe.get_all("File", filters={"attached_to_doctype": BIZ, "attached_to_name": name},
                                 fields=["file_name", "file_url", "is_private", "owner", "creation"])
    ff = {"status": biz.fulfillment_status, "owner": biz.fulfillment_owner,
          "due_at": biz.fulfillment_due_at, "completed_by": biz.completed_by, "completed_at": biz.completed_at,
          "summary": biz.fulfillment_summary, "output_link": biz.output_link,
          "completed_attachment": biz.completed_attachment,
          "operation_expected_completion_date": biz.operation_expected_completion_date,
          "operation_note": biz.operation_note, "asset_handover_note": biz.asset_handover_note}
    return {
        "business": biz.as_dict(),
        "approval": {"name": req.name if req else None,
                     "approval_status": req.approval_status if req else "Draft",
                     "current_level": req.current_level if req else 0,
                     "information_requested_from_level": req.information_requested_from_level if req else None,
                     "status_label": _STATUS_LABEL.get(req.approval_status if req else "Draft")},
        "levels": levels, "approvers": approvers, "attachments": attachments, "timeline": timeline,
        "fulfillment": ff,
        "process_preview": ([] if req else _process_preview(biz.approval_type or APPROVAL_TYPE)),
        "capabilities": _capabilities(user, biz, req),
    }


get_request_detail = get_detail


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #
@frappe.whitelist(methods=["POST"])
def save_draft(name=None, payload=None):
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    if name:
        doc = frappe.get_doc(BIZ, name)
        req = _req_of(name)
        if doc.requested_by != user and not _sm():
            frappe.throw(_("Ban chi co the sua yeu cau cua minh."), frappe.PermissionError)
        if req and req.approval_status not in ("Information Required",):
            frappe.throw(_("Chi co the sua yeu cau o trang thai Nhap hoac Can bo sung."))
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
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "capabilities": _capabilities(user, doc, _req_of(doc.name))}


@frappe.whitelist(methods=["POST"])
def submit_request(name):
    from ecentric_workspace.approval_center.asset_request import service as svc
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        approval_request = svc.submit(name)
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []
    return {"approval_request": approval_request, "submitted": True, "detail": get_detail(name)}


def _resolve_req(name):
    doc = frappe.get_doc(BIZ, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau nay chua duoc gui."))
    return doc, doc.approval_request


@frappe.whitelist(methods=["POST"])
def approve(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    doc, req = _resolve_req(name)
    engine.approve(req, comment=comment)
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def reject(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    doc, req = _resolve_req(name)
    engine.reject(req, comment=comment)
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def request_information(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    doc, req = _resolve_req(name)
    engine.request_information(req, comment=comment)
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def resubmit(name, payload=None):
    from ecentric_workspace.approval_center.asset_request import service as svc
    if payload:
        save_draft(name=name, payload=payload)
    res = svc.resubmit(name)
    return {"restarted": bool(res.get("restarted")), "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def cancel(name, reason=None):
    from ecentric_workspace.approval_center.engine import service as engine
    user = frappe.session.user
    doc = frappe.get_doc(BIZ, name)
    req = _req_of(name)
    if not _capabilities(user, doc, req)["can_cancel"]:
        frappe.throw(_("Ban khong duoc phep huy yeu cau nay."), frappe.PermissionError)
    if req:
        engine.cancel(req.name, reason=reason)
        return {"detail": get_detail(name)}
    frappe.delete_doc(BIZ, name, ignore_permissions=True)
    return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def admin_approve_current_level(name, reason=None):
    from ecentric_workspace.approval_center.engine import service as engine
    if not _sm():
        frappe.throw(_("Chi System Manager moi duoc duyet thay."), frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw(_("Vui long nhap ly do duyet thay."))
    doc, req_name = _resolve_req(name)
    if not _capabilities(frappe.session.user, doc, _req_of(name))["can_admin_approve_current_level"]:
        frappe.throw(_("Khong the duyet thay o trang thai hien tai."))
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        engine.admin_override_current_level(req_name, actor=frappe.session.user, reason=reason)
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []
    return {"admin_approved": True, "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name):
    from ecentric_workspace.approval_center.asset_request import service as svc
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        res = svc.claim_fulfillment(name)
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []
    return {"claimed": True, "owner": res.get("owner"), "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, payload=None):
    from ecentric_workspace.approval_center.asset_request import service as svc
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        svc.complete_fulfillment(name, payload=payload)
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []
    return {"completed": True, "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def set_operation_fields(name, operation_expected_completion_date=None, operation_note=None):
    from ecentric_workspace.approval_center.asset_request import service as svc
    svc.set_operation_fields(name, operation_expected_completion_date=operation_expected_completion_date,
                             operation_note=operation_note)
    return {"ok": True, "detail": get_detail(name)}
