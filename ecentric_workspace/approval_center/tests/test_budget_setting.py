# Copyright (c) 2026, eCentric and contributors
"""Budget Setting (Batch 8, merged Annual+Monthly) backend tests - REAL-USER via frappe.set_user.
Sequential HOF -> CEO. Covers: chain, non-approver + ordered blocks, Annual (Jan 1) / Monthly (day 1)
period validation, financial risk conditional, amounts >= 0, required attachment, auto-title per period.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_budget_setting
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import budget_setting as api
from ecentric_workspace.approval_center.budget_setting import setup as bsetup

PFX = "ZZBUD_"
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
    if not frappe.db.exists("Company", "ZZBUD Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZBUD Co", "abbr": "ZZBUDC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZBUD Co"


def _dept():
    if not frappe.db.exists("Department", {"department_name": "ZZBUD Dept"}):
        return frappe.get_doc({"doctype": "Department", "department_name": "ZZBUD Dept",
                               "company": _company()}).insert(ignore_permissions=True).name
    return frappe.db.get_value("Department", {"department_name": "ZZBUD Dept"}, "name")


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not n:
        n = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                            "company": _company(), "status": "Active", "gender": "Other",
                            "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
            ignore_permissions=True).name
    return n


def _todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _ensure():
    if not frappe.db.exists("EC Approval Type", "BUDGET_SETTING"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "BUDGET_SETTING",
                        "approval_title": "Budget Setting Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(HOF); _user(CEO)
    bsetup.setup_budget_setting_v1(hof=[HOF], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "BUDGET_SETTING-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"budget_period_type": "Annual", "period_start": "2027-01-01", "department": _dept(),
               "approved_budget_current_period": 100, "actual_spending_current_period": 50,
               "forecast_budget_next_period": 120, "forecast_justification": "growth",
               "has_financial_risks": "No", "request_attachment": "/private/files/b.pdf"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestBudgetSetting(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_chain_hof_then_ceo(self):
        req = _user(PFX + "req@example.com"); _employee(req)
        outsider = _user(PFX + "outsider@example.com")
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_todo(name, HOF))
        # CEO cannot approve while L1 pending; outsider blocked
        frappe.set_user(CEO)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")
        frappe.set_user(HOF); api.approve(name, comment="ok"); frappe.set_user("Administrator")
        self.assertTrue(_todo(name, CEO))
        frappe.set_user(CEO); api.approve(name, comment="ok"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith("Budget Setting - Annual"))

    def test_period_and_risk_validation(self):
        req = _user(PFX + "vreq@example.com"); _employee(req)
        # Annual not Jan 1 -> blocked
        n1 = _draft(req, budget_period_type="Annual", period_start="2027-03-01")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # Monthly not day 1 -> blocked
        n2 = _draft(req, budget_period_type="Monthly", period_start="2027-03-15")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # Monthly day 1 -> OK, title Monthly
        n3 = _draft(req, budget_period_type="Monthly", period_start="2027-03-01")
        frappe.set_user(req); api.submit_request(n3); frappe.set_user("Administrator")
        self.assertTrue((frappe.db.get_value(api.BIZ, n3, "request_title") or "").startswith("Budget Setting - Monthly"))
        # has_financial_risks Yes but no detail -> blocked
        n4 = _draft(req, has_financial_risks="Yes", financial_risk_details="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n4)
        frappe.set_user("Administrator")
        # negative amount -> blocked; missing attachment -> blocked
        for over in ({"forecast_budget_next_period": -1}, {"request_attachment": ""}):
            nn = _draft(req, **over)
            frappe.set_user(req)
            with self.assertRaises(Exception):
                api.submit_request(nn)
            frappe.set_user("Administrator")
