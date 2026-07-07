# Copyright (c) 2026, eCentric and contributors
"""Resignation orchestration over the shared approval engine. Business-type-specific:
requester context, email/date validation, material-change restart, and a post-approval
HR fulfillment queue (claim + complete with an HR processing note). Approvers/fulfillers
are resolved from EC Approval Process participants (config) - never hardcoded here.
L1 Direct Manager resolves from employee_email via the shared Reference Employee Manager
resolver (+ config fallback_user). No external integration."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Resignation Request"
APPROVAL_TYPE = "RESIGNATION"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["resignation_for", "employee_email", "personal_email", "last_working_day",
                   "resignation_reason"]
REQUIRED_AT_SUBMIT = ["request_title", "resignation_for", "employee_email", "personal_email",
                      "last_working_day", "resignation_reason", "workplace_environment_rating",
                      "benefit_policy_rating", "corporate_culture_rating"]
_RATING_FIELDS = ["workplace_environment_rating", "benefit_policy_rating", "corporate_culture_rating"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def _valid_rating(v):
    v = (v or "").strip()
    if not v:
        return False
    d = v[0]
    return d.isdigit() and 1 <= int(d) <= 5


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
    if not _EMAIL_RE.match((doc.employee_email or "").strip()):
        frappe.throw(_("Email cong ty (Employee Email) khong hop le."))
    if not _EMAIL_RE.match((doc.personal_email or "").strip()):
        frappe.throw(_("Email ca nhan (Personal Email) khong hop le."))
    for f in _RATING_FIELDS:
        if not _valid_rating(doc.get(f)):
            frappe.throw(_("Vui long chon danh gia (1-5) day du."))
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
# HR Fulfillment (post-final-approval queue) - dispatched by engine.complete_approval
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
        engine.assign(BUSINESS_DT, name, fulfillers, _("Resignation HR fulfillment queue"))
    engine.notify([doc.requested_by] + fulfillers,
                  _("Da duyet - chuyen HR xu ly: {0}").format(name), BUSINESS_DT, name)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name, user=None):
    """Idempotent claim. First claim of an Assigned request logs exactly one "Started" timeline
    entry; a repeat claim by the SAME owner returns success without a duplicate entry and without
    resetting owner/status; a claim while another user owns it is blocked. complete_fulfillment
    behavior is unchanged."""
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Ban khong thuoc nhom HR xu ly yeu cau nay."))
    cur = frappe.db.get_value(BUSINESS_DT, name,
                              ["fulfillment_status", "fulfillment_owner"], as_dict=True) or {}
    status, owner = cur.get("fulfillment_status"), cur.get("fulfillment_owner")
    # Idempotent: already claimed by this user -> no duplicate timeline, no state reset.
    if status == "In Progress" and owner == user:
        return {"owner": user, "claimed": True, "idempotent": True}
    # Already owned by someone else -> block (do not steal).
    if owner and owner != user:
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    if status == "Completed":
        frappe.throw(_("Yeu cau nay da hoan tat."))
    # Waiting (Assigned): atomic claim; the WHERE guard also settles concurrent double-claims.
    frappe.db.sql(
        """update `tabEC Resignation Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Resignation Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    engine.close_todos(BUSINESS_DT, name, keep_user=user)
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("HR fulfillment claimed"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("HR da nhan xu ly boi {0}: {1}").format(user, name),
                  BUSINESS_DT, name)
    return {"owner": user, "claimed": True}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chi nguoi nhan xu ly hoac System Manager moi duoc hoan tat."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui long nhap Ghi chu xu ly cua HR truoc khi hoan tat."))
    doc.fulfillment_summary = summary
    if "completed_attachment" in data:
        doc.completed_attachment = data.get("completed_attachment")
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    doc.save(ignore_permissions=True)
    engine.close_todos(BUSINESS_DT, name)
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Yeu cau nghi viec da hoan tat: {0}").format(name), BUSINESS_DT, name)
    return {"completed": True}
