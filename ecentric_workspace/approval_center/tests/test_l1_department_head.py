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


def _department(name, head_employee=None, manager_email=None):
    dep = frappe.db.get_value("Department", {"department_name": name}, "name")
    if dep:
        d = frappe.get_doc("Department", dep)
    else:
        d = frappe.get_doc({"doctype": "Department", "department_name": name}
                           ).insert(ignore_permissions=True)
    changed = False
    if hasattr(d, "department_head"):
        d.department_head = head_employee
        changed = True
    if manager_email is not None and hasattr(d, "manager_email"):
        d.manager_email = manager_email
        changed = True
    if changed:
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

    def test_manager_email_resolves_requester_as_head(self):
        """Live-site model (no department_head column): the requester manages a Department via
        Department.manager_email while their Employee.department is the reporting group
        ('Management - EC' analogue) -> the dynamic row must still resolve the requester."""
        if not frappe.db.has_column("Department", "manager_email"):
            self.skipTest("Department.manager_email custom field absent on this site")
        ceo = _user(PFX + "ceo2@example.com")
        req = _user(PFX + "head2@example.com")
        ceo_emp = _employee(ceo)
        grp = _department(PFX + "Reporting Group")          # analogue of 'Management - EC'
        _department(PFX + "Real Dept", manager_email=req)   # the dept the requester MANAGES
        _employee(req, department=grp, reports_to=ceo_emp)  # Employee.department = group, NOT real dept
        rows = [frappe._dict({"participant_purpose": "Approver",
                              "source_type": "Department Manager", "sort_order": -1,
                              "department": None, "fallback_user": None})]
        users = [u for (u, _label) in engine.resolve_participants(rows, req)]
        self.assertEqual(users, [req])                      # resolved via managed-dept lookup

    def test_validator_allows_department_manager_without_department(self):
        """Regression for the 2026-08-24 migrate failure: a dynamic 'Department Manager' row
        (department empty = requester's own department) must pass validation."""
        from ecentric_workspace.approval_center.shared.workflow.participants import validate_participants
        row = frappe._dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                            "user": None, "role": None, "department": None})
        validate_participants(frappe._dict({"participants": [row]}), "participants")  # must not throw
        static = frappe._dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                               "user": None, "role": None, "department": "Some Dept"})
        validate_participants(frappe._dict({"participants": [static]}), "participants")  # static form still OK
        bad = frappe._dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                            "user": "x@example.com", "role": None, "department": None})
        with self.assertRaises(frappe.ValidationError):
            validate_participants(frappe._dict({"participants": [bad]}), "participants")

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
