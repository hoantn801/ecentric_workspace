# Copyright (c) 2026, eCentric and contributors
"""Employee Information Update (Batch 7) backend tests: submit/approve chain, HR approver
snapshot, non-approver blocked, employee_email must resolve to an Employee, invalid employee
blocked, and NO automatic Employee/User master mutation (approval-only v1).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_employee_info_update
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import employee_info_update as api
from ecentric_workspace.approval_center.employee_info_update import setup as s

PFX = "ZZEIU_"
HR = PFX + "hr@example.com"
TARGET = PFX + "target@example.com"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZEIU Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZEIU Co", "abbr": "ZZEIUC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZEIU Co"


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        return n
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    _user(HR)
    _employee(TARGET)                    # so employee_email resolves by user_id
    s.setup_employee_info_update_v1(review_approvers=[HR], apply=1)
    frappe.db.set_value("EC Approval Process", "EMPLOYEE_INFO_UPDATE-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"employee_email": TARGET, "field_to_update": "Bank account",
               "current_value": "111", "new_value": "222"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestEmployeeInfoUpdate(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def setUp(self):
        _ensure()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def _requester(self):
        r = _user(PFX + "req@example.com"); _employee(r); return r

    def test_submit_hr_approve_and_snapshot(self):
        req = self._requester()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        approvers = frappe.get_all("EC Approval Request Approver",
                                   filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(HR, approvers)
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith(
            "Employee Info Update - " + TARGET + " - Bank account"))
        # non-approver blocked
        outsider = _user(PFX + "out@example.com")
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")
        # HR approves -> Approved
        frappe.set_user(HR); api.approve(name, comment="ok"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_employee_email_must_resolve(self):
        req = self._requester()
        name = _draft(req, employee_email=PFX + "nobody@nowhere.com")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_no_master_mutation_after_approval(self):
        req = self._requester()
        emp = frappe.db.get_value("Employee", {"user_id": TARGET}, "name")
        before = frappe.get_doc("Employee", emp).as_dict()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        frappe.set_user(HR); api.approve(name, comment="ok"); frappe.set_user("Administrator")
        after = frappe.get_doc("Employee", emp).as_dict()
        for f in ("employee_name", "bank_ac_no", "personal_email", "cell_number", "user_id"):
            self.assertEqual(before.get(f), after.get(f), "Employee master field %s must NOT be mutated" % f)
        # values are stored on the business doc instead
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "new_value"), "222")
