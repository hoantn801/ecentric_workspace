# Copyright (c) 2026, eCentric and contributors
"""Payment Request (Batch 8) backend tests - REAL-USER via frappe.set_user. Sequential chain
Direct Manager -> Finance -> HOF -> CEO. Covers: submit + full chain, non-approver + missing-manager
blocks, details_and_attachments_correct must be Yes, has_purchase_request Yes (linked PR must be
Approved) / No (reason required), amount>0, required attachment.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_payment_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as api
from ecentric_workspace.approval_center.api import purchase_request as papi
from ecentric_workspace.approval_center.payment_request import setup as psetup
from ecentric_workspace.approval_center.purchase_request import setup as prsetup
from ecentric_workspace.approval_center.tests import erp_fixtures as erp

PFX = "zzpay_"  # lowercase: frappe lowercases User.name; mixed-case desyncs set_user vs owner fields (fresh-site portability fix, 2026-07-12)
FIN = PFX + "fin@example.com"
HOF = PFX + "hof@example.com"
CEO = PFX + "ceo@example.com"


def _user(email, roles=("Employee",)):
    return erp.make_user(email, roles)


def _company():
    return erp.make_company("ZZPAY Co", "ZZPAYC")


def _dept():
    return erp.make_department("ZZPAY Dept", _company())


def _employee(user, reports_to=None):
    return erp.make_employee(user, _company(), reports_to=reports_to)


def _cat():
    if not frappe.db.exists("EC Approval Category", "ZZPAY_CAT"):
        frappe.get_doc({"doctype": "EC Approval Category", "category_code": "ZZPAY_CAT",
                        "category_name": "ZZPAY Test"}).insert(ignore_permissions=True)
    return "ZZPAY_CAT"


def _ensure():
    if not frappe.db.exists("EC Approval Type", "PAYMENT_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "PAYMENT_REQUEST",
                        "approval_title": "Payment Request", "card_status": "Coming Soon",
                        "process_status": "Discovery", "category": _cat()}).insert(ignore_permissions=True)
    _user(FIN); _user(HOF); _user(CEO)
    psetup.setup_payment_request_v1(finance=[FIN], hof=[HOF], ceo=[CEO], apply=1)
    psetup._upsert({2: [FIN], 3: [HOF], 4: [CEO]})  # self-contained across modules
    frappe.db.set_value("EC Approval Process", "PAYMENT_REQUEST-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"reason": "Vendor invoice", "payment_amount": 3000000, "payment_date": "2026-09-15",
               "payee_full_name": "ACME Ltd", "account_bank": "VCB", "bank_account_number": "0011",
               "has_purchase_request": "No", "no_purchase_request_reason": "Direct expense",
               "is_cost_valid": "Yes", "details_and_attachments_correct": "Yes",
               "request_attachment": "/private/files/inv.pdf"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestPaymentRequest(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_no_pr(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com"); _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")
        for u in (mgr, FIN, HOF, CEO):
            frappe.set_user(u); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_details_gate_and_conditionals(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        # details_and_attachments_correct = No -> blocked
        n1 = _draft(req, details_and_attachments_correct="No")   # confirmation unchecked -> blocked
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # has_purchase_request = No but no reason -> blocked
        n2 = _draft(req, has_purchase_request="No", no_purchase_request_reason="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # has_purchase_request = Yes but linked PR not Approved -> blocked
        if not frappe.db.exists("EC Approval Type", "PURCHASE_REQUEST"):
            frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "PURCHASE_REQUEST",
                            "approval_title": "Purchase Request", "card_status": "Coming Soon",
                            "category": _cat()}).insert(ignore_permissions=True)
        prsetup.setup_purchase_request_v1(finance=[FIN], hof=[HOF], ceo=[CEO], apply=1)
        frappe.db.set_value("EC Approval Process", "PURCHASE_REQUEST-V1", "status", "Active")
        frappe.set_user(req)
        pr = papi.save_draft(payload=frappe.as_json({
            "department": _dept(), "justification": "x", "purchase_details": "x", "payment_amount": 1000,
            "payment_term": "Pay within 7 days", "supplier_type": "Existing supplier", "supplier_name": "S",
            "additional_notes_comments": "n", "estimated_purchase_date": "2026-09-01",
            "estimated_delivery_date": "2026-09-02", "request_attachment": "/f.pdf"}))["name"]
        papi.submit_request(pr)                                  # PR now Pending (not Approved)
        n3 = _draft(req, has_purchase_request="Yes", purchase_request=pr, no_purchase_request_reason="")
        with self.assertRaises(Exception):
            api.submit_request(n3)                               # linked PR not Approved -> blocked
        frappe.set_user("Administrator")

    def test_missing_manager_and_amount_and_attachment(self):
        req = _user(PFX + "areq@example.com"); _employee(req)   # no manager
        n = _draft(req)
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n)                                # missing manager
        frappe.set_user("Administrator")
        mgr = _user(PFX + "amgr@example.com")
        req2 = _user(PFX + "areq2@example.com"); _employee(req2, reports_to=_employee(mgr))
        for over in ({"payment_amount": 0}, {"request_attachment": ""}):
            nn = _draft(req2, **over)
            frappe.set_user(req2)
            with self.assertRaises(Exception):
                api.submit_request(nn)
            frappe.set_user("Administrator")
