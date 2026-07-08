# Copyright (c) 2026, eCentric and contributors
"""Leave (Batch 6) backend tests - REAL-USER simulation via frappe.set_user. Single level:
Direct Manager Review -> Completed. Covers setup idempotency, submit/approve chain, next-approver
ToDo+DocShare, real audit actor, non-approver + missing-manager blocks, leave-type/date/duration
validation, 0.5 half-day, auto-title, optional attachment.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_leave
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import leave as api
from ecentric_workspace.approval_center.leave import setup as lsetup

PFX = "ZZLV_"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZLV Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZLV Co", "abbr": "ZZLVC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZLV Co"


def _employee(user, reports_to=None):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not n:
        n = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                            "company": _company(), "status": "Active", "gender": "Other",
                            "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
            ignore_permissions=True).name
    if reports_to:
        frappe.db.set_value("Employee", n, "reports_to", reports_to)
    return n


def _shared_with(name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": api.BIZ, "share_name": name, "user": user}))


def _open_todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _actions(ar, action):
    return frappe.get_all("EC Approval Action", filters={"approval_request": ar, "action": action}, pluck="actor")


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "LEAVE_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "LEAVE_REQUEST",
                        "approval_title": "Leave", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    lsetup.setup_leave_v1(apply=1)
    frappe.db.set_value("EC Approval Process", "LEAVE_REQUEST-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"leave_type": "Annual", "start_date": "2026-08-01", "end_date": "2026-08-03",
               "duration_days": 3}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestLeave(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_setup_idempotent(self):
        r = lsetup.setup_leave_v1(apply=1)
        self.assertIn(r["result"], ("APPLIED (process Draft; card inactive)", "ALREADY_ACTIVE"))
        self.assertTrue(lsetup.validate_leave_v1()["ok"])

    def test_full_chain_single_level(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(ar)                                          # business doc + approval request
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))
        # auto-title generated
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith("Leave - Annual"))

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertIn(mgr, _actions(ar, "Approved"))

    def test_missing_manager_blocked(self):
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        name = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_validation(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        # end before start
        n1 = _draft(req, start_date="2026-08-05", end_date="2026-08-01")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # duration <= 0
        n2 = _draft(req, duration_days=0)
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # 0.5 accepted + attachment not required (no attachment supplied) -> submits
        n3 = _draft(req, duration_days=0.5)
        frappe.set_user(req); api.submit_request(n3); frappe.set_user("Administrator")
        self.assertTrue(frappe.db.get_value(api.BIZ, n3, "approval_request"))
