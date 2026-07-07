# Copyright (c) 2026, eCentric and contributors
"""Promotion (Batch 4) backend tests - REAL-USER permission simulation via frappe.set_user.
Chain: requester -> Direct Manager -> CnB -> HOF -> CEO -> Completed. Also: non-approver blocked,
next approver gets ToDo + DocShare, audit actor is the real user, governance block when the
requester has no direct manager (salary-bearing form), and salary validation.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_promotion
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import promotion as api
from ecentric_workspace.approval_center.promotion import setup as psetup

PFX = "ZZPRM_"
CNB = PFX + "cnb@example.com"       # stands in for tuan.ly
HOF = PFX + "hof@example.com"       # stands in for phuong.nguyen1
CEO = PFX + "ceo@example.com"       # stands in for lam.nguyen


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZPRM Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZPRM Co", "abbr": "ZZPRMC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZPRM Co"


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
    if not frappe.db.exists("EC Approval Type", "PROMOTION_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "PROMOTION_REQUEST",
                        "approval_title": "Promotion Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(CNB); _user(HOF); _user(CEO)
    psetup.setup_promotion_v1(cnb=[CNB], hof=[HOF], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "PROMOTION_REQUEST-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "Promotion - X", "full_name": "Nguyen Van X", "department": _dept(),
               "current_position": "Exec", "proposed_position": "Lead",
               "justification": "Strong results.", "current_salary": 20000000,
               "proposed_salary": 30000000, "effective_date_of_promotion": "2026-10-01"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


def _dept():
    if not frappe.db.exists("Department", {"department_name": "ZZPRM Dept"}):
        d = frappe.get_doc({"doctype": "Department", "department_name": "ZZPRM Dept",
                            "company": _company()}).insert(ignore_permissions=True)
        return d.name
    return frappe.db.get_value("Department", {"department_name": "ZZPRM Dept"}, "name")


class TestPromotion(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_four_levels(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))   # Direct Manager assigned

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")

        # L1 Direct Manager
        frappe.set_user(mgr); api.approve(name, comment="ok mgr"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared_with(name, CNB) and _open_todo(name, CNB))   # next approver (CnB) assigned
        # L2 CnB, L3 HOF, L4 CEO
        frappe.set_user(CNB); api.approve(name, comment="cnb"); frappe.set_user("Administrator")
        frappe.set_user(HOF); api.approve(name, comment="hof"); frappe.set_user("Administrator")
        frappe.set_user(CEO); api.approve(name, comment="ceo"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        approvers = _actions(ar, "Approved")
        for u in (mgr, CNB, HOF, CEO):
            self.assertIn(u, approvers)      # audit actors are the real users
        self.assertEqual(frappe.db.get_value("EC Approval Action",
                         {"approval_request": ar, "level_no": 1, "action": "Approved"}, "actor"), mgr)

    def test_block_when_no_direct_manager(self):
        orphan = _user(PFX + "orphan@example.com")
        _employee(orphan)   # no reports_to
        name = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)          # governance block, friendly VI message
        frappe.set_user("Administrator")
        self.assertFalse(frappe.db.get_value(api.BIZ, name, "approval_request"))

    def test_salary_validation(self):
        req = _user(PFX + "vreq@example.com")
        _employee(req, reports_to=_employee(_user(PFX + "vmgr@example.com")))
        n1 = _draft(req, proposed_salary=-5)
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
