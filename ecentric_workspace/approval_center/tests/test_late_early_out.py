# Copyright (c) 2026, eCentric and contributors
"""Late in - Early out (Batch 6) backend tests - REAL-USER via frappe.set_user. Single level Direct
Manager Review -> Completed. Covers submit/approve chain, next-approver ToDo+DocShare, real audit
actor, non-approver + missing-manager blocks, check_time options, check_time_other conditional,
auto-title, optional attachment.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_late_early_out
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import late_early_out as api
from ecentric_workspace.approval_center.late_early_out import setup as lsetup

PFX = "ZZLE_"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZLE Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZLE Co", "abbr": "ZZLEC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZLE Co"


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


def _shared_with(name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": api.BIZ, "share_name": name, "user": user}))


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "LATE_EARLY_OUT"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "LATE_EARLY_OUT",
                        "approval_title": "Late in - Early out", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    lsetup.setup_late_early_out_v1(apply=1)
    frappe.db.set_value("EC Approval Process", "LATE_EARLY_OUT-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"applied_date": "2026-08-10", "request_type": "Đi trễ", "check_time": "10 AM", "reason": "Traffic"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestLateEarlyOut(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_and_autotitle(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith("Đi trễ - 2026-08-10 - 10 AM"))
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")
        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_check_time_other_conditional_and_missing_manager(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        # Other without other text -> blocked
        n1 = _draft(req, check_time="Other", check_time_other="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # Other WITH text -> submits, title uses the custom time (no attachment required)
        n2 = _draft(req, check_time="Other", check_time_other="9:30 AM")
        frappe.set_user(req); api.submit_request(n2); frappe.set_user("Administrator")
        self.assertTrue((frappe.db.get_value(api.BIZ, n2, "request_title") or "").endswith("9:30 AM"))
        # missing manager
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        n3 = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(n3)
        frappe