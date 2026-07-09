# Copyright (c) 2026, eCentric and contributors
"""Affiliate Bonus (Batch 8) backend tests - REAL-USER via frappe.set_user. Sequential
Vinh Review -> CEO Review. Covers: chain, non-approver + ordered blocks, service_month day-1
validation, total_amount>0, budget>=0, required attachment, auto-title.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_affiliate_bonus
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import affiliate_bonus as api
from ecentric_workspace.approval_center.affiliate_bonus import setup as asetup

PFX = "ZZAFB_"
VINH = PFX + "vinh@example.com"
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
    if not frappe.db.exists("Company", "ZZAFB Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZAFB Co", "abbr": "ZZAFBC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZAFB Co"


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
    if not frappe.db.exists("EC Approval Type", "AFFILIATE_BONUS_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "AFFILIATE_BONUS_REQUEST",
                        "approval_title": "Affiliate Bonus Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(VINH); _user(CEO)
    asetup.setup_affiliate_bonus_v1(vinh=[VINH], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "AFFILIATE_BONUS_REQUEST-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"service_month": "2026-09-01", "detail": "minigame + revenue; 5 KOCs",
               "total_amount": 8000000, "budget": 10000000, "request_attachment": "/private/files/a.pdf"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestAffiliateBonus(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_chain_vinh_then_ceo(self):
        req = _user(PFX + "req@example.com"); _employee(req)
        outsider = _user(PFX + "outsider@example.com")
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_todo(name, VINH))
        # CEO cannot approve while L1 pending; outsider blocked
        frappe.set_user(CEO)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")
        frappe.set_user(VINH); api.approve(name); frappe.set_user("Administrator")
        self.assertTrue(_todo(name, CEO))
        frappe.set_user(CEO); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertTrue((frappe.db.get_value(api.BIZ, name, "request_title") or "").startswith("Affiliate Bonus - 2026-09"))

    def test_validation(self):
        req = _user(PFX + "vreq@example.com"); _employee(req)
        for over in ({"service_month": "2026-09-15"},        # not day 1
                     {"total_amount": 0},                    # must be > 0
                     {"budget": -1},                         # >= 0
                     {"request_attachment": ""}):            # required attachment
            n = _draft(req, **over)
            frappe.set_user(req)
            with self.assertRaises(Exception):
                api.submit_request(n)
            frappe.set_user("Administrator")
