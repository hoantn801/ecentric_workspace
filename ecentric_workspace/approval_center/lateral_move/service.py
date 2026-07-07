# Copyright (c) 2026, eCentric and contributors
"""Employee Lateral Move orchestration over the shared engine.
Current Direct Manager -> New Line Manager -> HR -> CEO (no fulfillment). L1 resolves from
Employee.reports_to (blocked at submit if unresolved - no requester choice). L2 approver is the
User named in the new_line_manager field, resolved via the shared 'Reference User Field' source;
new_line_manager must be an active System User (validated at submit). No hardcoded runtime approvers."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Lateral Move Request"
APPROVAL_TYPE = "LATERAL_MOVE"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["new_position", "new_department", "new_line_manager", "transfer_reason", "start_date"]
REQUIRED_AT_SUBMIT = ["request_title", "new_position", "new_department", "new_line_manager",
                      "transfer_reason", "start_date"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _emp(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company", "reports_to"], as_dict=True)


def _is_active_system_user(user):
    row = user and frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def _direct_manager_user(emp):
    mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return mgr if (mgr and _is_active_system_user(mgr)) else None


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
    emp = _emp(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
        doc.current_department = emp.department
        mgr_now = emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
        doc.current_line_manager = mgr_now or None
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    # New line manager: must be a valid email AND an active System User (it is the L2 approver).
    nlm = (doc.new_line_manager or "").strip()
    if not _EMAIL_RE.match(nlm):
        frappe.throw(_("Email quan ly moi (New line manager) khong hop le."))
    if not _is_active_system_user(nlm):
        frappe.throw(_("Quan ly moi phai la nguoi dung dang hoat dong trong he thong. Vui long kiem tra email."))
    # Current Direct Manager must be resolvable (no requester choice, no silent bypass).
    if not _direct_manager_user(emp):
        frappe.throw(_("Khong xac dinh duoc Quan ly truc tiep hien tai cua ban. Vui long lien he HR/Admin de "
                       "cap nhat 'Bao cao cho' (reports_to) trong ho so nhan su truoc khi gui yeu cau."))
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
