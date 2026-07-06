# Copyright (c) 2026, eCentric and contributors
"""Daily Target (form #5) backend tests: scope -> process selection, approver
snapshot from config, required fields + attachment, first-of-month validation,
approval to Completed, no hardcoded approvers.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_daily_target
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import daily_target as api
from ecentric_workspace.approval_center.daily_target import setup as dtsetup

PFX = "ZZDT_"
CM = PFX + "cm@example.com"     # Commercial Manager (project)
CEO = PFX + "ceo@example.com"   # CEO (consolidated)


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZDT Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZDT Co", "abbr": "ZZDTC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZDT Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    if not frappe.db.exists("EC Approval Type", "DAILY_TARGET"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "DAILY_TARGET",
                        "approval_title": "Daily Target Setting", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(CM); _user(CEO)
    dtsetup.setup_daily_target_v1(project_approvers=[CM], consolidated_approvers=[CEO], apply=1)
    for code in (dtsetup.PROCESS_PROJECT, dtsetup.PROCESS_CONSOLIDATED):
        frappe.db.set_value("EC Approval Process", code, "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _draft(user, scope, **over):
    frappe.set_user(user)
    payload = {"request_title": "T", "request_scope": scope, "brand": "BrandX", "channels": "Shopee,Lazada",
               "target_month": "2026-08-01", "target_setting_type": "Setting new target",
               "justification": "attainable because ...", "request_attachment": "/files/x.xlsx"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestDailyTarget(FrappeTestCase):
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

    def _submit(self, scope):
        req = _requester()
        name = _draft(req, scope)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name

    def test_project_scope_uses_project_process(self):
        name = self._submit("Project level")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_process"),
                         dtsetup.PROCESS_PROJECT)
        l1 = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(CM, l1)                                # Commercial Manager from config

    def test_consolidated_scope_uses_consolidated_process(self):
        name = self._submit("Consolidated / Total")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_process"),
                         dtsetup.PROCESS_CONSOLIDATED)
        l1 = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(CEO, l1)                               # CEO from config

    def test_required_fields_enforced(self):
        req = _requester()
        name = _draft(req, "Project level", brand="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_attachment_required(self):
        req = _requester()
        name = _draft(req, "Project level", request_attachment="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_target_month_must_be_first_of_month(self):
        req = _requester()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_scope": "Project level", "brand": "B",
                "channels": "Shopee", "target_month": "2026-08-15",
                "target_setting_type": "Setting new target", "justification": "j",
                "request_attachment": "/f", "request_title": "T"}))
        frappe.set_user("Administrator")

    def test_approve_completes(self):
        name = self._submit("Project level")
        frappe.set_user(CM)
        api.approve(name, comment="ok")
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_setup_dry_run_vs_apply_and_no_hardcode(self):
        rep = dtsetup.setup_daily_target_v1(project_approvers=[CM], consolidated_approvers=[CEO],
                                            dry_run=1, apply=0)
        self.assertEqual(rep["mode"], "dry_run")
        # runtime resolution reads from participant config (snapshot), not hardcoded emails
        name = self._submit("Project level")
        ar = self._ar(name)
        src = frappe.get_all("EC Approval Request Approver",
                             filters={"approval_request": ar, "level_no": 1}, fields=["approver", "source"])
        self.assertTrue(all(r.source == "Configured User" for r in src))
