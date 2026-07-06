# Copyright (c) 2026, eCentric and contributors
"""Daily Target orchestration over the shared engine. One business DocType, two
scopes -> two configured Approval Processes (selected by scope; approvers still
come from process participants/snapshot). No fulfillment (v1); final approval =
Completed (engine terminal 'Approved')."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Daily Target Request"
APPROVAL_TYPE = "DAILY_TARGET"
PROCESS_PROJECT = "DAILY_TARGET_PROJECT-V1"
PROCESS_CONSOLIDATED = "DAILY_TARGET_CONSOLIDATED-V1"

MATERIAL_FIELDS = ["request_scope", "brand", "channels", "channel_other", "target_month",
                   "target_setting_type", "justification"]
REQUIRED_AT_SUBMIT = ["request_title", "request_scope", "brand", "channels", "target_month",
                      "target_setting_type", "justification", "request_attachment"]


def process_for_scope(scope):
    return PROCESS_PROJECT if scope == "Project level" else PROCESS_CONSOLIDATED


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


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
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    chans = [c.strip() for c in (doc.channels or "").split(",") if c.strip()]
    if "Other" in chans and not (doc.channel_other or "").strip():
        frappe.throw(_("Vui lòng nhập kênh khác khi chọn 'Other'."))
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user,
                             process_code=process_for_scope(doc.request_scope))
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
