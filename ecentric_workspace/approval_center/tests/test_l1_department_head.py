# Copyright (c) 2026, eCentric and contributors
"""L1 'Department Manager' candidate (p059): a department-head requester resolves as their own
L1 approver (self-sign of the 'Truong bo phan' area), CEO stays unique at L4 (no duplicate-skip
orphan). Resolver-level tests - the engine integration path is already covered by the b3 suite.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_l1_department_head
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.approval_center.patches import p059_l1_department_head_candidate as p059

PFX = "zz-l1dh-"


def _user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                        "send_welcome_email": 0, "roles": [{"role": "System Manager"}]}
                       ).insert(ignore_permissions=True)
    return email


def _employee(email, department=None, reports_to=None):
    name = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if name:
        emp = frappe.get_doc("Employee", name)
        emp.department = department
        emp.reports_to = reports_to
        emp.save(ignore_permissions=True)
        return emp.name
    emp = frappe.get_doc({"doctype": "Employee", "first_name": email.split("@")[0],
                          "status": "Active", "gender": "Male",
                          "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
                          "user_id": email, "department": department, "reports_to": reports_to}
                         ).insert(ignore_permissions=True)
    return emp.name


def _department(name, head_employee=None):
    dep = frappe.db.get_value("Department", {"department_name": name}, "name")
    if dep:
        d = frappe.get_doc("Department", dep)
    else:
        d = frappe.get_doc({"doctype": "Department", "department_name": name}
                           ).insert(ignore_permissions=True)
    if hasattr(d, "department_head"):
        d.department_head = head_employee
        d.save(ignore_permissions=True)
    return d.name


class TestL1DepartmentHead(FrappeTestCase):
    def test_department_manager_resolves_requester_as_head(self):
        ceo = _user(PFX + "ceo@example.com")
        req = _user(PFX + "head@example.com")
        ceo_emp = _employee(ceo)
        head_emp = _employee(req, reports_to=ceo_emp)
        dept = _department(PFX + "Data & System", head_employee=head_emp)
        _employee(req, department=dept, reports_to=ceo_emp)
        if not frappe.db.has_column("Department", "department_head"):
            self.skipTest("Department.department_head custom field absent on this site")
        rows = [frappe._dict({"participant_purpose": "Approver",
                              "source_type": "Department Manager", "sort_order": -1,
                              "department": None, "fallback_user": None}),
                frappe._dict({"participant_purpose": "Approver",
                              "source_type": "Requester Manager", "sort_order": 0,
                              "department": None, "fallback_user": None})]
        users = [u for (u, _label) in engine.resolve_participants(rows, req)]
        self.assertIn(req, users)                      # dept head (the requester) IS a candidate
        self.assertIn(ceo, users)                      # manager stays a candidate (Any One)

    def test_patch_idempotent(self):
        if not frappe.db.exists("EC Approval Process", "PAYMENT_REQUEST-V1"):
            self.skipTest("live process not seeded in CI site")
        p059.execute()
        p059.execute()                                 # second run must be a no-op
        lvl = frappe.get_all("EC Approval Level",
                             filters={"approval_process": "PAYMENT_REQUEST-V1", "level_no": 1},
                             pluck="name")[0]
        rows = frappe.get_all("EC Approval Participant",
                              filters={"parent": lvl, "source_type": "Department Manager",
                                       "participant_purpose": "Approver"})
        self.assertEqual(len(rows), 1)
