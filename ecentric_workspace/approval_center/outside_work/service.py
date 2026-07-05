# Copyright (c) 2026, eCentric and contributors
"""Outside Work orchestration glue over the generic approval engine.
Business-type-specific: requester + manager context, submit validation,
material-change restart on resubmit. No fulfillment, no attendance update (v1)."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Outside Work Request"
APPROVAL_TYPE = "OUTSIDE_WORK"

MATERIAL_FIELDS = ["work_type", "start_date", "end_date", "duration_days", "department"]
REQUIRED_AT_SUBMIT = ["request_title", "work_type", "start_date", "end_date", "duration_days", "remarks"]

MSG_NO_MANAGER = ("Bạn chưa có Quản lý trực tiếp trong hệ thống. "
                  "Vui lòng liên hệ HR/Admin để cập nhật trước khi gửi yêu cầu.")


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company", "reports_to"], as_dict=True)


def _manager_user(emp):
    if emp and emp.reports_to:
        return frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return None


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    # required fields at submit (drafts may be partial)
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc trước khi gửi."))
    # direct manager (friendly message wins over the engine's generic 'no approver resolved')
    mgr = _manager_user(emp)
    if not mgr:
        frappe.throw(_(MSG_NO_MANAGER))
    doc.direct_manager = mgr
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


def overlap_count(user, start_date, end_date, exclude=None):
    """Non-blocking light overlap check: other non-terminal requests for the same requester
    whose [start,end] overlaps [start_date,end_date]. Returns a count (never raises)."""
    if not (user and start_date and end_date):
        return 0
    rows = frappe.get_all(BUSINESS_DT,
                          filters={"requested_by": user, "start_date": ["<=", end_date],
                                   "end_date": [">=", start_date]},
                          fields=["name", "approval_request"])
    n = 0
    for r in rows:
        if exclude and r.name == exclude:
            continue
        st = r.approval_request and frappe.db.get_value("EC Approval Request", r.approval_request,
                                                        "approval_status")
        if st in ("Rejected", "Cancelled"):
            continue
        n += 1
    return n
