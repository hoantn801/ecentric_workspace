# Copyright (c) 2026, eCentric and contributors
"""Livestream Supplies (Batch 7) backend tests: submit/approve chain, approver snapshot,
non-approver blocked, quantity>0, end_date>=start_date, and comment-required-on-approve
enforced in THIS form's api.approve wrapper (shared engine untouched).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_livestream_supplies
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import livestream_supplies as api
from ecentric_workspace.approval_center.livestream_supplies import setup as s

PFX = "ZZLVS_"
APP = PFX + "sang@example.com"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZLVS Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZLVS Co", "abbr": "ZZLVSC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZLVS Co"


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        return n
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    _user(APP)
    s.setup_livestream_supplies_v1(review_approvers=[APP], apply=1)
    frappe.db.set_value("EC Approval Process", "LIVESTREAM_SUPPLIES-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"supplies": "Camera", "request_type": "Request supplies", "quantity": 2,
               "justification": "livestream event", "start_date": "2026-08-01", "end_date": "2026-08-02"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestLivestreamSupplies(FrappeTestCase):
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

    def test_submit_snapshot_title_and_approve(self):
        req = self._requester()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertIn(APP, frappe.get_all("EC Approval Request Approver",
                      filters={"approval_request": ar, "level_no": 1}, pluck="approver"))
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith(
            "Livestream Supplies - Request supplies - Camera"))
        outsider = _user(PFX + "out@example.com")
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")

    def test_quantity_and_date_validation(self):
        req = self._requester()
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(_draft(req, quantity=0))
        with self.assertRaises(Exception):
            api.submit_request(_draft(req, start_date="2026-08-05", end_date="2026-08-01"))
        frappe.set_user("Administrator")

    def test_approve_comment_required(self):
        req = self._requester()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        frappe.set_user(APP)
        with self.assertRaises(Exception):
            api.approve(name, comment="")          # empty comment blocked (form-level enforcement)
        api.approve(name, comment="approved ok")   # non-empty passes
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", self._ar(name), "approval_status"), "Approved")
