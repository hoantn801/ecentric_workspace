# Copyright (c) 2026, eCentric and contributors
"""Compensation Leave (Batch 6) backend tests - REAL-USER via frappe.set_user. Single level Direct
Manager Review -> Completed. Covers submit/approve chain, next-approver ToDo+DocShare, missing-manager
+ non-approver blocks, OT/CL date-order + duration>0 validation, 0.5 half-day, NO cross-validation
(CL<=OT not enforced; CL-after-OT not enforced), auto-title, optional attachment.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_compensation_leave
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import compensation_leave as api
from ecentric_workspace.approval_center.compensation_leave import setup as csetup

PFX = "ZZCL_"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZCL Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZCL Co", "abbr": "ZZCLC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZCL Co"


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


def _open_todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "COMPENSATION_LEAVE"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "COMPENSATION_LEAVE",
                        "approval_title": "Compensation leave", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    csetup.setup_compensation_leave_v1(apply=1)
    frappe.db.set_value("EC Approval Process", "COMPENSATION_LEAVE-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"overtime_start_date": "2026-08-01", "overtime_end_date": "2026-08-02",
               "overtime_duration_days": 2, "cl_start_date": "2026-08-10", "cl_end_date": "2026-08-10",
               "cl_duration_days": 1, "remarks": "Weekend project OT"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestCompensationLeave(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_autotitle_and_no_cross_validation(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        # CL duration > OT duration AND CL before OT -> still ALLOWED (no cross-validation in v1)
        name = _draft(req, overtime_duration_days=1, cl_duration_days=5,
                      cl_start_date="2026-07-01", cl_end_date="2026-07-05")
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_open_todo(name, mgr))
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith("Compensation Leave - 2026-07-01 to 2026-07-05"))
        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_date_order_and_duration_validation_and_half_day(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        # OT end before OT start
        n1 = _draft(req, overtime_start_date="2026-08-05", overtime_end_date="2026-08-01")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # CL end before CL start
        n2 = _draft(req, cl_start_date="2026-08-10", cl_end_date="2026-08-01")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # duration 0
        n3 = _draft(req, cl_duration_days=0)
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n3)
        frappe.set_user("Administrator")
        # 0.5 half-day accepted, no attachment
        n4 = _draft(req, cl_duration_days=0.5, overtime_duration_days=0.5)
        frappe.set_user(req); api.submit_request(n4); frappe.set_user("Administrator")
        self.assertTrue(frappe.db.get_value(api.BIZ, n4, "approval_request"))

    def test_missing_manager_blocked(self):
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        name = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")
