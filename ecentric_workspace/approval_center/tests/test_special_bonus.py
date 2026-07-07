# Copyright (c) 2026, eCentric and contributors
"""Special Bonus (Batch 5) backend tests - REAL-USER simulation via frappe.set_user.
Chain: requester -> Direct Manager -> CnB -> HOF -> CEO -> Completed. Also: non-approver blocked,
next approver gets ToDo + DocShare, audit actor is the real user, invalid department blocked, missing
direct manager blocked (money-bearing), required attachment enforced, setup idempotent.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_special_bonus
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import special_bonus as api
from ecentric_workspace.approval_center.special_bonus import setup as ssetup

PFX = "ZZSB_"
CNB = PFX + "cnb@example.com"
HOF = PFX + "hof@example.com"
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
    if not frappe.db.exists("Company", "ZZSB Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZSB Co", "abbr": "ZZSBC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZSB Co"


def _dept():
    if not frappe.db.exists("Department", {"department_name": "ZZSB Dept"}):
        return frappe.get_doc({"doctype": "Department", "department_name": "ZZSB Dept",
                               "company": _company()}).insert(ignore_permissions=True).name
    return frappe.db.get_value("Department", {"department_name": "ZZSB Dept"}, "name")


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
    if not frappe.db.exists("EC Approval Type", "SPECIAL_BONUS"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "SPECIAL_BONUS",
                        "approval_title": "Special Bonus", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(CNB); _user(HOF); _user(CEO)
    ssetup.setup_special_bonus_v1(cnb=[CNB], hof=[HOF], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "SPECIAL_BONUS-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "Bonus - X", "department": _dept(), "project_name": "Apollo",
               "reasons": "Outstanding delivery.", "total_bonus": 5000000,
               "request_attachment": "/private/files/evidence.pdf"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestSpecialBonus(FrappeTestCase):
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
        r1 = ssetup.setup_special_bonus_v1(cnb=[CNB], hof=[HOF], ceo=[CEO], apply=1)
        self.assertIn(r1["result"], ("APPLIED (process Draft; card inactive)", "ALREADY_ACTIVE"))
        v = ssetup.validate_special_bonus_v1()
        self.assertTrue(v["ok"], [c for c in v["checks"] if not c["ok"]])

    def test_full_chain_four_levels(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared_with(name, CNB) and _open_todo(name, CNB))
        frappe.set_user(CNB); api.approve(name); frappe.set_user("Administrator")
        frappe.set_user(HOF); api.approve(name); frappe.set_user("Administrator")
        frappe.set_user(CEO); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        approvers = _actions(ar, "Approved")
        for u in (mgr, CNB, HOF, CEO):
            self.assertIn(u, approvers)

    def test_invalid_department_blocked(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        name = _draft(req, department="TOTALLY_NOT_A_DEPT")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_missing_manager_blocked(self):
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        name = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_required_attachment(self):
        mgr = _user(PFX + "amgr@example.com")
        req = _user(PFX + "areq@example.com"); _employee(req, reports_to=_employee(mgr))
        name = _draft(req, request_attachment="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")
