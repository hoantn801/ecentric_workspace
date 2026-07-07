# Copyright (c) 2026, eCentric and contributors
"""Promotion orchestration over the shared engine. Direct Manager -> CnB -> HOF -> CEO
(User participants from process config; no fulfillment). Governance: because a promotion
carries salary data, the Direct Manager approver is NEVER requester-chosen - it resolves
from Employee.reports_to. If it cannot be resolved, submit is blocked with a friendly
Vietnamese message (no silent bypass). No hardcoded runtime approvers."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Promotion Request"
APPROVAL_TYPE = "PROMOTION_REQUEST"

MATERIAL_FIELDS = ["full_name", "department", "current_position", "proposed_position",
                   "justification", "current_salary", "proposed_salary", "incentives",
                   "effective_date_of_promotion"]
REQUIRED_AT_SUBMIT = ["request_title", "full_name", "department", "current_position",
                      "proposed_position", "justification", "effective_date_of_promotion"]
_SALARY_FIELDS = ["current_salary", "proposed_salary"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


def _direct_manager_user(user):
    """Requester's direct manager (reports_to -> user_id) if an active System User, else None."""
    emp = frappe.db.get_value("Employee", {"user_id": user}, ["name", "reports_to"], as_dict=True)
    mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
    if mgr:
        row = frappe.db.get_value("User", mgr, ["enabled", "user_type"], as_dict=True)
        if row and row.enabled and row.user_type == "System User":
            return mgr
    return None


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
    emp = _ctx(user)
    if emp:
        doc.employee = emp.name
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if doc.current_salary is None:
        missing.append("current_salary")
    if doc.proposed_salary is None:
        missing.append("proposed_salary")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    for f in _SALARY_FIELDS:
        try:
            if float(doc.get(f)) < 0:
                frappe.throw(_("Muc luong khong the la so am."))
        except (TypeError, ValueError):
            frappe.throw(_("Muc luong phai la so."))
    # Governance block: Direct Manager must be resolvable (salary-bearing form; no requester choice).
    if not _direct_manager_user(user):
        frappe.throw(_("Khong xac dinh duoc Quan ly truc tiep cua ban. Vui long lien he HR/Admin de cap "
                       "nhat 'Bao cao cho' (reports_to) trong ho so nhan su truoc khi gui yeu cau thang chuc."))
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
