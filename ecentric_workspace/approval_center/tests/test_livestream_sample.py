# Copyright (c) 2026, eCentric and contributors
"""Livestream Sample (form #10) backend tests: single-level Sang Bui approval,
config snapshot, attachment optional, required fields, no fulfillment, no hardcoded
runtime approvers.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_livestream_sample
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import livestream_sample as api
from ecentric_workspace.approval_center.livestream_sample import setup as ls
from ecentric_workspace.approval_center.patches import p021_backfill_livestream_sample_type as p021

PFX = "ZZLS_"
SANG = PFX + "sang@example.com"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZLS Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZLS Co", "abbr": "ZZLSC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZLS Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure():
    if not frappe.db.exists("EC Approval Type", "LIVESTREAM_SAMPLE"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "LIVESTREAM_SAMPLE",
                        "approval_title": "Livestream Sample Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(SANG)
    ls.setup_livestream_sample_v1(reviewer=[SANG], apply=1)
    frappe.db.set_value("EC Approval Process", "LIVESTREAM_SAMPLE-V1", "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "T", "brand": "BrandX", "sample_detail": "SKU 123 x5",
               "estimated_arrival_time": "2026-08-01"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestLivestreamSample(FrappeTestCase):
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

    def test_single_level_and_complete(self):
        name = self._submit()
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        l1 = frappe.get_all("EC Approval Request Approver", filters={"approval_request": ar, "level_no": 1}, fields=["approver", "source"])
        self.assertIn(SANG, [x.approver for x in l1])           # Sang Bui from config
        self.assertTrue(all(x.source == "Configured User" for x in l1))
        self.assertEqual(frappe.db.count("EC Approval Request Level", {"approval_request": ar}), 1)   # no fulfillment level
        frappe.set_user(SANG); api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_attachment_optional(self):
        req = _requester()
        name = _draft(req)                                      # no attachment
        frappe.set_user(req)
        api.submit_request(name)                                # must succeed without attachment
        frappe.set_user("Administrator")
        self.assertTrue(self._ar(name))

    def test_required_fields(self):
        req = _requester()
        name = _draft(req, brand="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)
        frappe.set_user("Administrator")


class TestLivestreamSampleTypeBackfill(FrappeTestCase):
    """p021 back-fills EC Approval Type LIVESTREAM_SAMPLE (skipped by p018 because OTHERS did not
    exist yet), so setup can proceed."""

    def test_p021_creates_type_then_setup_passes(self):
        # simulate the live state: OTHERS category present, type missing
        if frappe.db.exists("EC Approval Type", "LIVESTREAM_SAMPLE"):
            frappe.delete_doc("EC Approval Type", "LIVESTREAM_SAMPLE", ignore_permissions=True, force=1)
        p021.execute()
        self.assertTrue(frappe.db.exists("EC Approval Type", "LIVESTREAM_SAMPLE"))
        row = frappe.db.get_value("EC Approval Type", "LIVESTREAM_SAMPLE",
                                  ["category", "card_status", "approval_title"], as_dict=True)
        self.assertEqual(row.category, "OTHERS")                 # under Others
        self.assertEqual(row.card_status, "Coming Soon")         # unpublished
        self.assertEqual(row.approval_title, "Livestream Sample Request")
        self.assertTrue(frappe.db.exists("EC Approval Category", "OTHERS"))
        # idempotent + admin edit preserved
        frappe.db.set_value("EC Approval Type", "LIVESTREAM_SAMPLE", "card_status", "Migrating")
        before = frappe.db.count("EC Approval Type")
        p021.execute()
        self.assertEqual(frappe.db.count("EC Approval Type"), before)
        self.assertEqual(frappe.db.get_value("EC Approval Type", "LIVESTREAM_SAMPLE", "card_status"), "Migrating")
        # setup can now proceed
        _user(SANG)
        rep = ls.setup_livestream_sample_v1(reviewer=[SANG], apply=1)
        self.assertIn(rep.get("result"), ("APPLIED (process Draft; card inactive)", "ALREADY_ACTIVE"))
        self.assertTrue(frappe.db.exists("EC Approval Process", "LIVESTREAM_SAMPLE-V1"))
