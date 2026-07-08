# Copyright (c) 2026, eCentric and contributors
"""Service Referral (Batch 7) backend tests: Any One L1 (Linh + Vinh both snapshotted;
either can approve+complete; the other cannot after completion; non-approver blocked),
estimated_contract_value>=0, optional contact_email validated only when provided,
flexible contact_phone_number.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_service_referral
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import service_referral as api
from ecentric_workspace.approval_center.service_referral import setup as s

PFX = "ZZSRF_"
A1 = PFX + "linh@example.com"
A2 = PFX + "vinh@example.com"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZSRF Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZSRF Co", "abbr": "ZZSRFC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZSRF Co"


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        return n
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    _user(A1); _user(A2)
    s.setup_service_referral_v1(review_approvers=[A1, A2], apply=1)
    frappe.db.set_value("EC Approval Process", "SERVICE_REFERRAL-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"client": "ACME", "brand": "BrandX", "contact_name": "John",
               "estimated_contract_value": 1000}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestServiceReferral(FrappeTestCase):
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

    def _submit(self):
        req = self._requester()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        return name

    def test_any_one_both_snapshotted_either_completes(self):
        name = self._submit()
        ar = self._ar(name)
        approvers = frappe.get_all("EC Approval Request Approver",
                                   filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(A1, approvers)
        self.assertIn(A2, approvers)   # both snapshotted at L1
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith(
            "Service Referral - ACME - BrandX"))
        # non-approver blocked
        outsider = _user(PFX + "out@example.com")
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")
        # A1 approves -> completed (Any One)
        frappe.set_user(A1); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        # A2 cannot approve after the level is already completed
        frappe.set_user(A2)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

    def test_value_and_optional_email_validation(self):
        req = self._requester()
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(_draft(req, estimated_contract_value=-1))     # value>=0
        with self.assertRaises(Exception):
            api.submit_request(_draft(req, contact_email="not-an-email"))    # bad email blocked
        # blank email OK; valid email OK; flexible phone OK
        api.submit_request(_draft(req, contact_email="", contact_phone_number="+84 090-111 222"))
        api.submit_request(_draft(req, contact_email="ok@x.com"))
        frappe.set_user("Administrator")
