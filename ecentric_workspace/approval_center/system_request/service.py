# Copyright (c) 2026, eCentric and contributors
"""Data Request orchestration glue over the generic approval engine.
Business-type-specific: requester context, material-change restart, and a
post-approval fulfillment queue (claim + complete). Approvers/fulfillers are
resolved from EC Approval Process participants (config) - never hardcoded here.
No external integration; fulfillment writes only this business record."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC System Request"
APPROVAL_TYPE = "SYSTEM_REQUEST"

MATERIAL_FIELDS = ["request_type", "other_type", "description", "priority",
                   "requester_expected_resolution_date"]
REQUIRED_AT_SUBMIT = ["request_title", "request_type", "description", "priority",
                      "requester_expected_resolution_date"]


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
        frappe.throw(_("Yeu cau nay da duoc gui."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Ban chi co the gui yeu cau cua chinh minh."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if doc.request_type == "Other" and not (doc.other_type or "").strip():
        frappe.throw(_("Vui long nhap loai yeu cau khac khi chon 'Other'."))
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
        frappe.throw(_("Yeu cau chua duoc gui."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


# --------------------------------------------------------------------------- #
# Fulfillment (post-final-approval queue) - dispatched by engine.complete_approval
# --------------------------------------------------------------------------- #
def on_final_approval(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    emp = frappe.db.get_value("Employee", {"user_id": doc.requested_by}, ["name", "company"], as_dict=True)
    sla = engine.resolve_sla(proc.fulfillment_sla_policy,
                             employee=emp.name if emp else None,
                             company=(emp.company if emp else None) or doc.company)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_due_at": sla["due_at"] if sla else None,
        "fulfillment_sla_calendar": sla["calendar"] if sla else None,
        "fulfillment_sla_holiday_list": sla["holiday_list"] if sla else None,
    })
    if fulfillers:
        engine.assign(BUSINESS_DT, name, fulfillers, _("System Request fulfillment queue"))
    engine.notify([doc.requested_by] + fulfillers,
                  _("Da duyet - chuyen Operation xu ly: {0}").format(name), BUSINESS_DT, name)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name, user=None):
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Ban khong thuoc nhom Operation xu ly yeu cau nay."))
    frappe.db.sql(
        """update `tabEC System Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC System Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    engine.close_todos(BUSINESS_DT, name, keep_user=user)
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("Fulfillment claimed"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("Operation da nhan xu ly boi {0}: {1}").format(user, name),
                  BUSINESS_DT, name)
    return {"owner": user}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chi nguoi nhan xu ly hoac System Manager moi duoc hoan tat."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui long nhap Tom tat ket qua xu ly truoc khi hoan tat."))
    doc.fulfillment_summary = summary
    if "output_link" in data:
        doc.output_link = data.get("output_link")
    if "completed_attachment" in data:
        doc.completed_attachment = data.get("completed_attachment")
    if data.get("operation_expected_completion_date"):
        doc.operation_expected_completion_date = data.get("operation_expected_completion_date")
    if "operation_note" in data:
        doc.operation_note = data.get("operation_note")
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    doc.save(ignore_permissions=True)
    engine.close_todos(BUSINESS_DT, name)
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("System Request da hoan tat: {0}").format(name), BUSINESS_DT, name)
    return {"completed": True}


@frappe.whitelist(methods=["POST"])
def set_operation_fields(name, operation_expected_completion_date=None, operation_note=None):
    """Operation records/updates the expected completion date + note (visible to the
    requester). Never auto-defaulted. Allowed: a current Operation approver, the
    fulfillment owner / an eligible fulfiller, or a System Manager."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    user = frappe.session.user
    allowed = "System Manager" in frappe.get_roles(user)
    if not allowed and doc.approval_request:
        cl = frappe.db.get_value("EC Approval Request", doc.approval_request, "current_level")
        if cl and engine._actor_pending_row(doc.approval_request, cl, user):
            allowed = True
    if not allowed and doc.fulfillment_owner == user:
        allowed = True
    if not allowed and frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                                 "allocated_to": user, "status": "Open"}):
        allowed = True
    if not allowed:
        frappe.throw(_("Chi Operation moi duoc cap nhat thoi gian du kien."))
    vals = {}
    if operation_expected_completion_date is not None:
        vals["operation_expected_completion_date"] = operation_expected_completion_date or None
    if operation_note is not None:
        vals["operation_note"] = operation_note
    if vals:
        frappe.db.set_value(BUSINESS_DT, name, vals)
    return {"ok": True, "operation_expected_completion_date": frappe.db.get_value(
        BUSINESS_DT, name, "operation_expected_completion_date")}
