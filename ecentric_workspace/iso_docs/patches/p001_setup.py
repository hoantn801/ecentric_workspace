# Copyright (c) 2026, eCentric and contributors
"""p001: dung nen Thu vien tai lieu ISO tren Quality Procedure (PO Hoan chot 04/10/2026).

KHONG sua DocType goc. Patch lo phan khong phai schema module (2 DocType con tu dong bo theo
module ISO Docs):
    1. 36 Custom Field ec_* - lay tu CHINH fixtures/custom_field.json (mot nguon), chi tao field
       con thieu (fixtures co the dong bo sau patch tren bench moi).
    2. 2 Role: Ban ISO, TGD duyet tai lieu (chua gan ai - Hoan gan tren /app/user).
    3. Property Setter: dat ten ban ghi theo ma tai lieu (autoname field:ec_doc_code). Site chua
       co Quality Procedure nao (kiem 04/10) nen khong ban ghi nao bi doi ten.
    4. Custom DocPerm: Desk User chi con DOC (truoc la toan quyen - ai co desk cung sua / xoa duoc
       tai lieu); Ban ISO toan quyen; TGD doc + ghi; Employee doc + ghi (has_permission thu hep:
       chi nguoi soan khi Nhap, truong BP khi cho minh duyet).
    5. Workflow "Tai lieu ISO" (workflow_spec.py) - chay lai thi lam moi theo dac ta.

Chay lai bao nhieu lan cung duoc. FAIL-SAFE: loi mot buoc -> Error Log, khong chan migrate.
"""
import json
import os

import frappe

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import workflow_spec as W

TITLE = "iso_docs p001 setup"


def execute():
    if not frappe.db.exists("DocType", C.QP):
        return
    for step in (_custom_fields, _roles, _autoname, _perms, _workflow):
        try:
            step()
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, step.__name__))
    frappe.clear_cache(doctype=C.QP)


def fixture_fields():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "custom_field.json")
    with open(path, encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("dt") == C.QP]


def _custom_fields():
    for row in fixture_fields():
        if frappe.db.exists("Custom Field", row["name"]):
            continue
        doc = frappe.get_doc(dict(row))
        doc.insert(ignore_permissions=True)


def _roles():
    for role in (C.ROLE_ISO, C.ROLE_CEO):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True)


def _autoname():
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    make_property_setter(C.QP, None, "autoname", "field:ec_doc_code", "Data", for_doctype=True)
    make_property_setter(C.QP, None, "naming_rule", "By fieldname", "Data", for_doctype=True)


PERM_ROWS = (
    (C.ROLE_ISO, ("read", "write", "create", "delete", "report", "export", "print", "share")),
    (C.ROLE_CEO, ("read", "write", "report", "print")),
    (C.ROLE_EMPLOYEE, ("read", "write")),
)
_ALL = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export",
        "import", "print", "email", "share")


def _perms():
    from frappe.permissions import setup_custom_perms

    # Chua co Custom DocPerm nao -> chep quyen chuan sang truoc (System Manager giu nguyen).
    setup_custom_perms(C.QP)
    for name in frappe.get_all("Custom DocPerm", filters={"parent": C.QP, "role": "Desk User"},
                               pluck="name"):
        frappe.db.set_value("Custom DocPerm", name, {p: 0 for p in _ALL if p != "read"})
    for role, ptypes in PERM_ROWS:
        if frappe.db.exists("Custom DocPerm", {"parent": C.QP, "role": role, "permlevel": 0,
                                               "if_owner": 0}):
            continue
        row = {"doctype": "Custom DocPerm", "parent": C.QP, "parenttype": "DocType",
               "parentfield": "permissions", "role": role, "permlevel": 0}
        row.update({p: 1 for p in ptypes})
        frappe.get_doc(row).insert(ignore_permissions=True)


def _workflow():
    for state, style in W.STATES:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state,
                            "style": style}).insert(ignore_permissions=True)
    for action in W.ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({"doctype": "Workflow Action Master",
                            "workflow_action_name": action}).insert(ignore_permissions=True)
    if frappe.db.exists("Workflow", C.WORKFLOW_NAME):
        wf = frappe.get_doc("Workflow", C.WORKFLOW_NAME)
    else:
        wf = frappe.new_doc("Workflow")
        wf.workflow_name = C.WORKFLOW_NAME
    wf.document_type = C.QP
    wf.is_active = 1
    wf.workflow_state_field = C.STATE_FIELD
    wf.send_email_alert = 0
    wf.override_status = 0
    wf.set("states", [])
    for state, role in W.EDIT_ROLES:
        wf.append("states", {"state": state, "doc_status": "0", "allow_edit": role})
    wf.set("transitions", [])
    for frm, action, to, role, cond in W.TRANSITIONS:
        wf.append("transitions", {"state": frm, "action": action, "next_state": to,
                                  "allowed": role, "condition": cond or None,
                                  "allow_self_approval": 1})
    wf.save(ignore_permissions=True)
