# Copyright (c) 2026, eCentric and contributors
"""Asset Damage or Loss orchestration over the shared engine. Operation Review (Any One of the
configured operation reviewers) -> CEO (no fulfillment). Approvers come from process config; no
requester choice and no manager resolution at any level. Conditional-required fields follow the
System Request 'Other' pattern. recommended_actions is a comma-joined multi-select (frontend
checkboxes) validated against the allowed set. Evidence attachment required."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Asset Damage Loss Request"
APPROVAL_TYPE = "ASSET_DAMAGE_LOSS"

ASSET_TYPES = ["Laptop", "Desktop computer", "Monitor", "Mobile device", "Printer", "RAM", "Other"]
INCIDENT_TYPES = ["Damage", "Loss", "Theft", "Other"]
RECOMMENDED_ACTIONS = ["Repair", "Replace", "Write-off", "Further investigation", "Other"]

MATERIAL_FIELDS = ["asset_type", "asset_type_other", "asset_code", "incident_type", "incident_type_other",
                   "incident_description", "incident_date", "incident_location", "physical_damage",
                   "data_compromised", "impact_on_operations", "estimated_repair_cost",
                   "estimated_value_lost_stolen_asset", "recommended_actions", "recommended_actions_other"]
REQUIRED_AT_SUBMIT = ["request_title", "asset_type", "asset_code", "incident_type", "incident_description",
                      "incident_date", "incident_location", "physical_damage", "data_compromised",
                      "impact_on_operations", "recommended_actions", "request_attachment"]
_COST_FIELDS = ["estimated_repair_cost", "estimated_value_lost_stolen_asset"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


def _actions_list(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


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
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    for f in _COST_FIELDS:
        if doc.get(f) is None:
            missing.append(f)
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc (bao gom tep dinh kem) truoc khi gui."))
    # Conditional-required 'Other' fields (System Request pattern).
    if doc.asset_type == "Other" and not (doc.asset_type_other or "").strip():
        frappe.throw(_("Vui long nhap loai tai san khac khi chon 'Other'."))
    if doc.incident_type == "Other" and not (doc.incident_type_other or "").strip():
        frappe.throw(_("Vui long nhap loai su co khac khi chon 'Other'."))
    # recommended_actions: comma-joined multi-select validated against the allowed set.
    picks = _actions_list(doc.recommended_actions)
    if not picks:
        frappe.throw(_("Vui long chon it nhat mot hanh dong de xuat."))
    bad = [p for p in picks if p not in RECOMMENDED_ACTIONS]
    if bad:
        frappe.throw(_("Hanh dong de xuat khong hop le: {0}.").format(", ".join(bad)))
    if "Other" in picks and not (doc.recommended_actions_other or "").strip():
        frappe.throw(_("Vui long nhap hanh dong de xuat khac khi chon 'Other'."))
    for f in _COST_FIELDS:
        try:
            if float(doc.get(f)) < 0:
                frappe.throw(_("Chi phi khong the la so am."))
        except (TypeError, ValueError):
            frappe.throw(_("Chi phi phai la so."))
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
