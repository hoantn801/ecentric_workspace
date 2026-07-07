# Copyright (c) 2026, eCentric and contributors
"""HR Activity (form #8) backend tests: multi-level chain HR Manager -> HOF -> CEO,
approver snapshots from config, attachment required, date + budget validation, no
hardcoded runtime approvers.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_hr_activity
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import hr_activity as api
from ecentric_workspace.approval_center.hr_activity import setup as hs

PFX = "ZZHR_"
HRM = PFX + "hrm@example.com"
HOF = PFX + "hof@example.com"
CEO = PFX + "ceo@example.com"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZHR Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZHR Co", "abbr": "ZZHRC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZHR Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    if not frappe.db.exists("EC Approval Type", "HR_ACTIVITY"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "HR_ACTIVITY",
                        "approval_title": "HR Activity", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(HRM); _user(HOF); _user(CEO)
    hs.setup_hr_activity_v1(hr_manager=[HRM], hof=[HOF], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "HR_ACTIVITY-V1", "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "T", "activity_type": "Company trip", "detail": "trip",
               "start_date": "2026-09-01", "end_date": "2026-09-03", "participants": "all",
               "justification": "morale", "estimated_budget": 5000000, "vendor_trainer_partner_info": "vendor X",
               "request_attachment": "/files/x.pdf"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestHRActivity(FrappeTestCase):
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

    def _submit(self):
        req = _requester()
        name = _draft(req)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name

    def test_full_chain(self):
        name = self._submit()
        ar = self._ar(name)
        l1 = frappe.get_all("EC Approval Request Approver", filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(HRM, l1)                              # HR Manager from config
        src = frappe.get_all("EC Approval Request Approver", filters={"approval_request": ar, "level_no": 1}, fields=["source"])
        self.assertTrue(all(x.source == "Configured User" for x in src))   # no runtime hardcoding
        frappe.set_user(HRM); api.approve(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        frappe.set_user(HOF); api.approve(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 3)
        frappe.set_user(CEO); api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_attachment_required(self):
        req = _requester(); name = _draft(req, request_attachment="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_required_fields(self):
        req = _requester(); name = _draft(req, justification="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_end_before_start_blocked(self):
        req = _requester()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "activity_type": "Company trip",
                "detail": "d", "start_date": "2026-09-10", "end_date": "2026-09-01", "participants": "p",
                "justification": "j", "estimated_budget": 1, "vendor_trainer_partner_info": "v", "request_attachment": "/f"}))
        frappe.set_user("Administrator")

    def test_negative_budget_blocked(self):
        req = _requester()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "activity_type": "Company trip",
                "detail": "d", "start_date": "2026-09-01", "end_date": "2026-09-03", "participants": "p",
                "justification": "j", "estimated_budget": -1, "vendor_trainer_partner_info": "v", "request_attachment": "/f"}))
        frappe.set_user("Administrator")
