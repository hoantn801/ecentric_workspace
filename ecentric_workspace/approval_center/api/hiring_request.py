# Copyright (c) 2026, eCentric and contributors
"""Permission-safe read + write API for Hiring Request. Mirrors AI Topup
conventions; NO fulfillment. Backend is authoritative; capability flags are advisory
(writes re-validate in the engine/service). Friendly Vietnamese errors only."""
import frappe
from frappe import _

BIZ = "EC Hiring Request"
APPROVAL_TYPE = "HIRING_REQUEST"
MAX_PAGE = 50
OPEN = ("Pending", "Information Required")
TERMINAL = ("Approved", "Rejected", "Cancelled")

_EDITABLE_DRAFT = ("request_title", "position", "number_of_vacancy", "reason", "employment_type",
                   "education", "department", "line_manager", "suggested_salary",
                   "request_attachment", "company")

_STATUS_LABEL = {"Draft": "Nháp", "Pending": "Đang phê duyệt", "Information Required": "Cần bổ sung",
                 "Approved": "Đã duyệt", "Rejected": "Bị từ chối", "Cancelled": "Đã hủy"}


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
                     "my_approvals": _has_any_approver_row(user) or _sm()},
            "form_options": get_form_options()}


def _department_options():
    """Selectable Department master records (value = Department.name, label = readable name).
    Excludes disabled/group departments when those fields exist (field-absence tolerant)."""
    filters = {}
    meta = frappe.get_meta("Department")
    if meta.has_field("disabled"):
        filters["disabled"] = 0
    if meta.has_field("is_group"):
        filters["is_group"] = 0
    rows = frappe.get_all("Department", filters=filters, fields=["name", "department_name"],
                          order_by="department_name asc", limit_page_length=0)
    return [{"value": r.name, "label": r.department_name or r.name} for r in rows]


@frappe.whitelist()
def get_form_options():
    return {"departments": _department_options(),
            "reasons": ["New", "Replace"],
            "employment_types": ["Full-time", "Freelancer", "Intern"]}


@frappe.whitelist()
def list_my_requests(filters=None, start=0, page_length=20):
    user = frappe.session.user
    flt = {"requested_by": user}
    f = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if f.get("employment_type"):
        flt["employment_type"] = f["employment_type"]
    if f.get("from_date") and f.get("to_date"):
        flt["creation"] = ["between", [f["from_date"], f["to_date"]]]
    page_length = min(int(page_length or 20), MAX_PAGE)
    total = frappe.db.count(BIZ, flt)
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "request_title", "position", "department", "number_of_vacancy",
                                  "employment_type", "approval_request", "creation", "modified"],
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
                                  ["reference_name", "approval_status", "current_level", "requested_by"], as_dict=True)
        if not req:
            continue
        if section == "pending" and (req.approval_status not in OPEN or req.current_level != r.level_no):
            continue
        biz = frappe.db.get_value(BIZ, req.reference_name,
                                  ["name", "request_title", "position", "department",
                                   "number_of_vacancy", "employment_type"], as_dict=True)
        if biz:
            cur_name = (frappe.db.get_value("EC Approval Request Level",
                        {"approval_request": r.approval_request, "level_no": req.current_level}, "level_name")
                        if req.current_level else None)
            biz.update({"approval_request": r.approval_request, "level_no": r.level_no,
                        "approval_status": req.approval_status, "current_level": req.current_level,
                        "current_level_name": cur_name, "requested_by": req.requested_by, "my_status": r.status,
                        "total_levels": frappe.db.count("EC Approval Request Level",
                                                        {"approval_request": r.approval_request})})
            out.append(biz)
    return {"rows": out}


# keep AI-Topup-style alias too
list_my_approvals = list_need_my_approval


@frappe.whitelist()
def get_detail(name):
    user = frappe.session.user
    biz = frappe.get_doc(BIZ, name)
    req = _req_of(name)
    if not _can_view(user, biz, req):
        frappe.throw(_("Bạn không có quyền xem yêu cầu này."), frappe.PermissionError)
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
    return {
        "business": biz.as_dict(),
        "approval": {"name": req.name if req else None,
                     "approval_status": req.approval_status if req else "Draft",
                     "current_level": req.current_level if req else 0,
                     "information_requested_from_level": req.information_requested_from_level if req else None,
                     "status_label": _STATUS_LABEL.get(req.approval_status if req else "Draft")},
        "levels": levels, "approvers": approvers, "attachments": attachments, "timeline": timeline,
        "process_preview": ([] if req else _process_preview(biz.approval_type or APPROVAL_TYPE)),
        "capabilities": _capabilities(user, biz, req),
    }


# alias
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
            frappe.throw(_("Bạn chỉ có thể sửa yêu cầu của mình."), frappe.PermissionError)
        if req and req.approval_status not in ("Information Required",):
            frappe.throw(_("Chỉ có thể sửa yêu cầu ở trạng thái Nháp hoặc Cần bổ sung."))
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
    from ecentric_workspace.approval_center.hiring_request import service as svc
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
        frappe.throw(_("Yêu cầu này chưa được gửi."))
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
    from ecentric_workspace.approval_center.hiring_request import service as svc
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
        frappe.throw(_("Bạn không được phép hủy yêu cầu này."), frappe.PermissionError)
    if req:
        engine.cancel(req.name, reason=reason)
        return {"detail": get_detail(name)}
    frappe.delete_doc(BIZ, name, ignore_permissions=True)
    return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def admin_approve_current_level(name, reason=None):
    from ecentric_workspace.approval_center.engine import service as engine
    if not _sm():
        frappe.throw(_("Chỉ System Manager mới được duyệt thay."), frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw(_("Vui lòng nhập lý do duyệt thay."))
    doc, req_name = _resolve_req(name)
    if not _capabilities(frappe.session.user, doc, _req_of(name))["can_admin_approve_current_level"]:
        frappe.throw(_("Không thể duyệt thay ở trạng thái hiện tại."))
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        engine.admin_override_current_level(req_name, actor=frappe.session.user, reason=reason)
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []
    return {"admin_approved": True, "detail": get_detail(name)}
