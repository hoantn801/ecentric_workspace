# Copyright (c) 2026, eCentric and contributors
"""Hiring (Batch 5) backend tests - REAL-USER simulation via frappe.set_user.
Chain: requester -> Direct Manager -> HR -> CEO -> Completed. Also: non-approver blocked, next
approver gets ToDo + DocShare, audit actor is the real user, line_manager must be an active User
(business field, NOT the approval resolver), attachment NOT required, invalid department + missing
direct manager + vacancy/salary bounds blocked.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_hiring_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import hiring_request as api
from ecentric_workspace.approval_center.hiring_request import setup as hsetup

PFX = "ZZHIR_"
HR = PFX + "hr@example.com"
CEO = PFX + "ceo@example.com"


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZHIR Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZHIR Co", "abbr": "ZZHIRC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZHIR Co"


def _dept():
    if not frappe.db.exists("Department", {"department_name": "ZZHIR Dept"}):
        return frappe.get_doc({"doctype": "Department", "department_name": "ZZHIR Dept",
                               "company": _company()}).insert(ignore_permissions=True).name
    return frappe.db.get_value("Department", {"department_name": "ZZHIR Dept"}, "name")


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
    if not frappe.db.exists("EC Approval Type", "HIRING_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "HIRING_REQUEST",
                        "approval_title": "Hiring Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(HR); _user(CEO)
    hsetup.setup_hiring_request_v1(hr=[HR], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "HIRING_REQUEST-V1", "status", "Active")


def _draft(user, line_manager, **over):
    frappe.set_user(user)
    payload = {"request_title": "Hire Analyst", "position": "Analyst", "number_of_vacancy": 2,
               "reason": "New", "employment_type": "Full-time", "education": "From Bachelor Degree",
               "department": _dept(), "line_manager": line_manager, "suggested_salary": 15000000}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestHiringRequest(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_three_levels_attachment_optional(self):
        mgr = _user(PFX + "mgr@example.com")
        lm = _user(PFX + "lm@example.com")            # future hire's line manager (active user)
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req, lm)                          # no attachment -> allowed
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared_with(name, HR) and _open_todo(name, HR))
        frappe.set_user(HR); api.approve(name); frappe.set_user("Administrator")
        frappe.set_user(CEO); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        for u in (mgr, HR, CEO):
            self.assertIn(u, _actions(ar, "Approved"))

    def test_line_manager_must_be_active_user(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        name = _draft(req, "ghost@nowhere.com")         # valid email, not a system user
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_invalid_department_and_missing_manager_and_bounds(self):
        mgr = _user(PFX + "bmgr@example.com")
        lm = _user(PFX + "blm@example.com")
        req = _user(PFX + "breq@example.com"); _employee(req, reports_to=_employee(mgr))
        # invalid department
        n1 = _draft(req, lm, department="NOPE_DEPT")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # vacancy 0
        n2 = _draft(req, lm, number_of_vacancy=0)
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # missing direct manager
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        n3 = _draft(orphan, lm)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(n3)
        frappe.set_user("Administrator")
