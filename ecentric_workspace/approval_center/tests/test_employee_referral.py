# Copyright (c) 2026, eCentric and contributors
"""Employee Referral (form #9) backend tests: Careers -> CEO chain, config snapshot,
email validation, relationship Other, attachment required, no Department for Careers,
no hardcoded runtime approvers.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_employee_referral
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import employee_referral as api
from ecentric_workspace.approval_center.employee_referral import setup as es

PFX = "ZZER_"
CAR = PFX + "careers@example.com"
CEO = PFX + "ceo@example.com"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZER Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZER Co", "abbr": "ZZERC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZER Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    if not frappe.db.exists("EC Approval Type", "EMPLOYEE_REFERRAL"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "EMPLOYEE_REFERRAL",
                        "approval_title": "Employee Referral", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(CAR); _user(CEO)
    es.setup_employee_referral_v1(careers=[CAR], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "EMPLOYEE_REFERRAL-V1", "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "T", "candidate_full_name": "Nguyen A", "candidate_email": "a@x.com",
               "position_applied_for": "Backend Dev", "hiring_department": "Engineering",
               "relationship_with_referrer": "Friend", "referral_justification": "great fit",
               "request_attachment": "/files/cv.pdf"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestEmployeeReferral(FrappeTestCase):
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

    def _submit(self):
        req = _requester()
        name = _draft(req)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name

    def test_chain_and_config_snapshot(self):
        name = self._submit()
        ar = self._ar(name)
        l1 = frappe.get_all("EC Approval Request Approver", filters={"approval_request": ar, "level_no": 1}, fields=["approver", "source"])
        self.assertIn(CAR, [x.approver for x in l1])            # Careers from config
        self.assertTrue(all(x.source == "Configured User" for x in l1))
        frappe.set_user(CAR); api.approve(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        frappe.set_user(CEO); api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_no_department_created_for_careers(self):
        self._submit()
        self.assertFalse(frappe.db.exists("Department", {"department_name": "Careers"}))

    def test_invalid_email_blocked(self):
        req = _requester()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "candidate_full_name": "A",
                "candidate_email": "not-an-email", "position_applied_for": "Dev", "hiring_department": "Eng",
                "relationship_with_referrer": "Friend", "referral_justification": "j", "request_attachment": "/f"}))
        frappe.set_user("Administrator")

    def test_relationship_other_required(self):
        req = _requester()
        name = _draft(req, relationship_with_referrer="Other", relationship_other="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_attachment_required(self):
        req = _requester(); name = _draft(req, request_attachment="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)
