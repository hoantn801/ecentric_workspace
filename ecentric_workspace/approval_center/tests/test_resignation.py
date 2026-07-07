# Copyright (c) 2026, eCentric and contributors
"""Resignation (Batch 4) backend tests - REAL-USER permission simulation via frappe.set_user.
Chain: requester submits -> Direct Manager (resolved from employee_email via Reference Employee
Manager) approves -> HR fulfiller completes -> Completed. Also: non-approver blocked, next
approver/fulfiller gets ToDo + DocShare, audit actor is the real user, config fallback_user when
the resigning employee has no manager, and field validation (email/date/rating).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_resignation
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import resignation as api
from ecentric_workspace.approval_center.resignation import setup as rsetup

PFX = "ZZRSN_"
HR = PFX + "hr@example.com"          # HR fulfiller (config seed, stands in for tuan.ly)
FB = PFX + "fallback@example.com"    # config fallback_user


def _user(email, roles=("Employee",)):
    """Active System User with ONLY the Employee role - NO generic Share permission."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZRSN Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZRSN Co", "abbr": "ZZRSNC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZRSN Co"


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
    if not frappe.db.exists("EC Approval Type", "RESIGNATION"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "RESIGNATION",
                        "approval_title": "Resignation Requests", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(HR); _user(FB)
    rsetup.setup_resignation_v1(hr_fulfillers=[HR], fallback_user=FB, apply=1)
    frappe.db.set_value("EC Approval Process", "RESIGNATION-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "Resignation Request_ODS_Test", "resignation_for": "Myself",
               "employee_email": user, "personal_email": "me@personal.com",
               "last_working_day": "2026-09-30", "resignation_reason": "Have another direction",
               "workplace_environment_rating": "5 (Very satisfied)",
               "benefit_policy_rating": "4 (Satisfied)", "corporate_culture_rating": "5 (Very satisfied)"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestResignation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    # ------------------------------------------------------------------ #
    # Full chain: Direct Manager approves (real user) -> HR fulfiller completes
    # ------------------------------------------------------------------ #
    def test_full_chain_direct_manager_then_hr(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        mgr_emp = _employee(mgr)
        _employee(req, reports_to=mgr_emp)
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)                       # Myself -> employee_email = req -> manager = mgr
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(_shared_with(name, mgr))   # Direct Manager got access + ToDo at submit
        self.assertTrue(_open_todo(name, mgr))

        # non-approver blocked
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

        # Direct Manager approves as the REAL user (no Share perm) -> final approval -> HR fulfillment
        frappe.set_user(mgr)
        api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertIn(mgr, _actions(ar, "Approved"))           # audit actor is the real approver
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")
        self.assertTrue(_shared_with(name, HR))                # HR fulfiller received access + ToDo
        self.assertTrue(_open_todo(name, HR))

        # HR claims + completes (HR processing note required)
        frappe.set_user(HR)
        with self.assertRaises(Exception):
            api.complete_fulfillment(name, payload=frappe.as_json({}))   # summary required
        api.claim_fulfillment(name)
        api.complete_fulfillment(name, payload=frappe.as_json({"fulfillment_summary": "Offboarded; assets returned."}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Completed")

    # ------------------------------------------------------------------ #
    # Config fallback_user when the resigning employee has no manager
    # ------------------------------------------------------------------ #
    def test_fallback_user_when_no_manager(self):
        orphan = _user(PFX + "orphan@example.com")
        _employee(orphan)                        # no reports_to
        name = _draft(orphan)
        frappe.set_user(orphan)
        api.submit_request(name)
        frappe.set_user("Administrator")
        # L1 resolved to the configured fallback (FB), not left empty
        self.assertTrue(_open_todo(name, FB))
        frappe.set_user(FB)
        api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def test_validation_email_date_rating(self):
        req = _user(PFX + "vreq@example.com")
        _employee(req, reports_to=_employee(_user(PFX + "vmgr@example.com")))
        # bad company email
        n1 = _draft(req, employee_email="not-an-email")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # bad personal email
        n2 = _draft(req, personal_email="nope")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # missing rating
        n3 = _draft(req, workplace_environment_rating="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n3)
        frappe.set_user("Administrator")
