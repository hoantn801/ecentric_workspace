# Copyright (c) 2026, eCentric and contributors
"""Permission-safe read + write API for Service Referral (Batch 7). Single level "Referral Review"
(Any One of the configured pool, e.g. Linh + Vinh). Authorization is governed entirely by the
Approval Center engine + the approval-request snapshot (pending-approver rows) - NOT by DocPerm on the
business DocType. A pending approver can approve through this API without holding broad Share/write
permission; the engine performs the state change and the onward share/ToDo via its hardened path.
Friendly Vietnamese errors only."""
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center.api._common import requester_display

BIZ = "EC Service Referral Request"
APPROVAL_TYPE = "SERVICE_REFERRAL"
MAX_PAGE = 50
OPEN = ("Pending", "Information Required")
TERMINAL = ("Approved", "Rejected", "Cancelled")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_EDITABLE_DRAFT = ("client", "brand", "contact_name", "contact_phone_number", "contact_email",
                   "estimated_contract_value", "justification", "request_attachment", "department", "company")
_REQUIRED = ("client", "brand", "contact_name")

_STATUS_LABEL = {"Draft": "Nháp", "Pending": "Đang phê duyệt", "Information Required": "Cần bổ sung",
                 "Approved": "Đã duyệt", "Rejected": "Bị từ chối", "Cancelled": "Đã hủy"}


def gen_title(doc):
    return ("Service Referral - %s - %s" % (doc.get("client") or "?", doc.get("brand") or "?"))[:180]


# --------------------------------------------------------------------------- #
# Permission-safe context helpers (all use frappe.db - no DocPerm dependency)
# --------------------------------------------------------------------------- #
def _sm():
    return "System Manager" in frappe.get_roles(frappe.session.user)


def _employee_ctx(user=None):
    user = user or frappe.session.user
    emp = frappe.db.get_value("Employee", {"user_id": user},
                              ["name", "employee_name", "department", "company"], as_dict=True)
    return {"user": user, "employee": emp.name if emp else None,
            "employee_name": emp.employee_name if emp else None,
            "department": emp.department if emp else None, "company": emp.company if emp else None}


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


def _is_snapshot_approver(req, user):
    """True if the user is in the approval-request snapshot for this request (any level/status).
    Grants read access to the request they are (or were) asked to act on - no DocPerm needed."""
    return bool(req and frappe.db.exists("EC Approval Request Approver",
                                         {"approval_request": req.name, "approver": user}))


def _can_view(user, requested_by, req):
    return requested_by == user or _sm() or _is_snapshot_approver(req, user)


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


def _capabilities(user, requested_by, req):
    is_requester = requested_by == user
    open_ = req and req.approval_status in OPEN
    can_act = bool(_pending_row(req, user))          # governs Approve/Reject/Request Info
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


@frappe.whitelist()
def get_form_options():
    return {}


@frappe.whitelist()
def list_my_requests(filters=None, start=0, page_length=20):
    user = frappe.session.user
    flt = {"requested_by": user}
    f = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if f.get("brand"):
        flt["brand"] = f["brand"]
    if f.get("from_date") and f.get("to_date"):
        flt["creation"] = ["between", [f["from_date"], f["to_date"]]]
    page_length = min(int(page_length or 20), MAX_PAGE)
    total = frappe.db.count(BIZ, flt)
    rows = frappe.get_all(BIZ, filters=flt,
                          fields=["name", "request_title", "client", "brand", "estimated_contract_value",
                                  "approval_request", "creation", "modified"],
                          limit_start=int(start), limit_page_length=page_length, order_by="modified desc")
    alc = None
    for r in rows:
        ar = r.approval_request and frappe.db.get_value(
            "EC Approval Request", r.approval_request, ["approval_status", "current_level"], as_dict=True)
        r["approval_status"] = ar.approval_status if ar else "Draft"
        r["current_level"] = ar.current_level if ar else 0
        r["requested_at"] = r.get("creation")
        r["requester_name"] = requester_display(user)
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
                                  ["name", "request_title", "client", "brand", "estimated_contract_value",
                                   "department", "creation"], as_dict=True)
        if biz:
            cur_name = (frappe.db.get_value("EC Approval Request Level",
                        {"approval_request": r.approval_request, "level_no": req.current_level}, "level_name")
                        if req.current_level else None)
            biz["requested_at"] = biz.get("creation")
            biz["requester_name"] = requester_display(req.requested_by)
            biz.update({"approval_request": r.approval_request, "level_no": r.level_no,
                        "approval_status": req.approval_status, "current_level": req.current_level,
                        "current_level_name": cur_name, "requested_by": req.requested_by, "my_status": r.status,
                        "total_levels": frappe.db.count("EC Approval Request Level",
                                                        {"approval_request": r.approval_request})})
            out.append(biz)
    return {"rows": out}


list_my_approvals = list_need_my_approval


@frappe.whitelist()
def get_detail(name):
    """Authorize via the approval-request context FIRST (frappe.db, no DocPerm), then read the
    business record. A pending/snapshot approver, the requester, or a System Manager can view -
    no broad Share/read permission on EC Service Referral Request is required."""
    user = frappe.session.user
    requested_by = frappe.db.get_value(BIZ, name, "requested_by")
    if requested_by is None and not frappe.db.exists(BIZ, name):
        frappe.throw(_("Không tìm thấy yêu cầu."))
    req = _req_of(name)
    if not _can_view(user, requested_by, req):
        frappe.throw(_("Bạn không có quyền xem yêu cầu này."), frappe.PermissionError)
    biz = frappe.get_doc(BIZ, name)   # governed read - authorization already established above
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
        lvl_by_name = {l.name: l for l in frappe.get_all(
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
        "capabilities": _capabilities(user, requested_by, req),
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
    doc.request_title = gen_title(doc)
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "capabilities": _capabilities(user, doc.requested_by, _req_of(doc.name))}


def _validate_for_submit(doc):
    missing = [f for f in _REQUIRED if not (doc.get(f) or "").strip()]
    if doc.estimated_contract_value is None:
        missing.append("estimated_contract_value")
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc trước khi gửi."))
    try:
        if float(doc.estimated_contract_value) < 0:
            frappe.throw(_("Giá trị hợp đồng dự kiến không thể là số âm."))
    except (TypeError, ValueError):
        frappe.throw(_("Giá trị hợp đồng dự kiến phải là số."))
    email = (doc.contact_email or "").strip()
    if email and not _EMAIL_RE.match(email):
        frappe.throw(_("Email liên hệ không hợp lệ."))


@frappe.whitelist(methods=["POST"])
def submit_request(name):
    from ecentric_workspace.approval_center.engine import service as engine
    from frappe.utils import now_datetime
    user = frappe.session.user
    doc = frappe.get_doc(BIZ, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if doc.requested_by and doc.requested_by != user and not _sm():
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."), frappe.PermissionError)
    doc.requested_by = doc.requested_by or user
    ctx = _employee_ctx(doc.requested_by)
    doc.employee = ctx["employee"]
    doc.department = doc.department or ctx["department"]
    doc.company = doc.company or ctx["company"]
    _validate_for_submit(doc)
    doc.request_title = gen_title(doc)
    doc.submitted_at = now_datetime()
    doc.save(ignore_permissions=True)
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        # engine.submit builds the snapshot (both pool approvers), activates L1 and grants each
        # pending approver a ToDo + read DocShare via the hardened engine path.
        approval_request = engine.submit(BIZ, doc.name, APPROVAL_TYPE, doc.requested_by)
    finally:
        frappe.flags.mute_messages = prev
    frappe.db.set_value(BIZ, doc.name, "approval_request", approval_request)
    frappe.local.message_log = []
    return {"approval_request": approval_request, "submitted": True, "detail": get_detail(name)}


def _resolve_req(name):
    """Resolve the approval-request name WITHOUT loading the business doc through a permission gate.
    Returns the EC Approval Request name; the engine authorizes the actor (pending-approver check)."""
    ar = frappe.db.get_value(BIZ, name, "approval_request")
    if not ar:
        frappe.throw(_("Yêu cầu này chưa được gửi."))
    return ar


def _muted(fn):
    prev = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        fn()
    finally:
        frappe.flags.mute_messages = prev
    frappe.local.message_log = []


@frappe.whitelist(methods=["POST"])
def approve(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    req = _resolve_req(name)
    _muted(lambda: engine.approve(req, comment=comment))   # engine authorizes: must be a pending approver
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def reject(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    req = _resolve_req(name)
    _muted(lambda: engine.reject(req, comment=comment))
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def request_information(name, comment=None):
    from ecentric_workspace.approval_center.engine import service as engine
    req = _resolve_req(name)
    _muted(lambda: engine.request_information(req, comment=comment))
    return {"detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def resubmit(name, payload=None):
    from ecentric_workspace.approval_center.engine import service as engine
    if payload:
        save_draft(name=name, payload=payload)
    req = _resolve_req(name)
    frappe.db.set_value(BIZ, name, "request_title", gen_title(frappe.get_doc(BIZ, name)))
    _muted(lambda: engine.resubmit(req, actor=frappe.session.user))
    return {"restarted": True, "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def cancel(name, reason=None):
    from ecentric_workspace.approval_center.engine import service as engine
    user = frappe.session.user
    requested_by = frappe.db.get_value(BIZ, name, "requested_by")
    req = _req_of(name)
    if not _capabilities(user, requested_by, req)["can_cancel"]:
        frappe.throw(_("Bạn không được phép hủy yêu cầu này."), frappe.PermissionError)
    if req:
        _muted(lambda: engine.cancel(req.name, reason=reason))
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
    req = _resolve_req(name)
    if not _capabilities(frappe.session.user, frappe.db.get_value(BIZ, name, "requested_by"),
                         _req_of(name))["can_admin_approve_current_level"]:
        frappe.throw(_("Không thể duyệt thay ở trạng thái hiện tại."))
    _muted(lambda: engine.admin_override_current_level(req, actor=frappe.session.user, reason=reason))
    return {"admin_approved": True, "detail": get_detail(name)}
