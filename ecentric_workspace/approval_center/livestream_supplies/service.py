# Copyright (c) 2026, eCentric and contributors
"""EC Livestream Supplies Request orchestration over the shared approval engine. Fixed-participant single
level (Sang Bui Review); approvers come from EC Approval Process config, never hardcoded
here. Approval-only v1: NO external integration, NO master-data mutation."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Livestream Supplies Request"
APPROVAL_TYPE = "LIVESTREAM_SUPPLIES"

MATERIAL_FIELDS = ["supplies", "request_type", "quantity", "justification", "start_date", "end_date"]
REQUIRED_AT_SUBMIT = ["supplies", "request_type", "quantity", "justification", "start_date", "end_date"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def gen_title(doc):
    a = (doc.get("request_type") or "?")
    b = (doc.get("supplies") or "?")
    return ("Livestream Supplies - %s - %s" % (a, b))[:180]


def _validate_business(doc):
    """Form-specific submit-time validation (friendly Vietnamese)."""
    if (doc.get("request_type") or "") not in ("Request supplies", "Return supplies"):
        frappe.throw(_("Vui long chon loai yeu cau (Request supplies / Return supplies)."))
    try:
        qty = int(doc.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        frappe.throw(_("So luong phai lon hon 0."))
    sd, ed = doc.get("start_date"), doc.get("end_date")
    if sd and ed and str(ed) < str(sd):
        frappe.throw(_("Ngay ket thuc khong duoc truoc ngay bat dau."))


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
    _validate_business(doc)
    doc.request_title = gen_title(doc)
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
    changed = new_sig != (doc.material_signature or "")
    frappe.db.set_value(BUSINESS_DT, doc.name, "request_title", gen_title(doc))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": changed}
