# Copyright (c) 2026, eCentric and contributors
"""Purchase Request (Batch 8) backend tests - REAL-USER via frappe.set_user. Sequential chain
Direct Manager -> Finance -> HOF -> CEO. Covers: submit, ordered approval (a later-level approver
cannot approve while an earlier level is pending), next-approver ToDo+DocShare, real audit actor,
non-approver + missing-manager blocks, dept/amount/date/conditional validation, required attachment.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_purchase_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import purchase_request as api
from ecentric_workspace.approval_center.purchase_request import setup as psetup
from ecentric_workspace.approval_center.tests import erp_fixtures as erp

PFX = "zzpur_"  # lowercase (frappe lowercases User.name); ERPNext-compatible fixtures via erp_fixtures
FIN = PFX + "fin@example.com"
HOF = PFX + "hof@example.com"
CEO = PFX + "ceo@example.com"


def _user(email, roles=("Employee",)):
    return erp.make_user(email, roles)


def _company():
    return erp.make_company("ZZPUR Co", "ZZPURC")


def _dept():
    return erp.make_department("ZZPUR Dept", _company())


def _employee(user, reports_to=None):
    return erp.make_employee(user, _company(), reports_to=reports_to)


def _shared(name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": api.BIZ, "share_name": name, "user": user}))


def _todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _actions(ar, action):
    return frappe.get_all("EC Approval Action", filters={"approval_request": ar, "action": action}, pluck="actor")


def _ensure():
    if not frappe.db.exists("EC Approval Type", "PURCHASE_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "PURCHASE_REQUEST",
                        "approval_title": "Purchase Request", "card_status": "Coming Soon",
                        "process_status": "Discovery",
                        "category": erp.ensure_category("ZZPUR_CAT", "ZZPUR Test")}).insert(ignore_permissions=True)
    _user(FIN); _user(HOF); _user(CEO)
    psetup.setup_purchase_request_v1(finance=[FIN], hof=[HOF], ceo=[CEO], apply=1)
    psetup._upsert({2: [FIN], 3: [HOF], 4: [CEO]})  # self-contained across modules
    frappe.db.set_value("EC Approval Process", "PURCHASE_REQUEST-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"department": _dept(), "justification": "Need it", "purchase_details": "Item x1",
               "payment_amount": 5000000, "payment_term": "Pay within 7 days", "supplier_type": "Existing supplier",
               "supplier_name": "ACME", "additional_notes_comments": "warranty 12m",
               "estimated_purchase_date": "2026-09-01", "estimated_delivery_date": "2026-09-10",
               "request_attachment": "/private/files/q.pdf"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestPurchaseRequest(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_sequential_chain(self):
        mgr = _user(PFX + "mgr@example.com")
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertTrue(_shared(name, mgr) and _todo(name, mgr))

        # non-approver blocked; Finance (L2) CANNOT approve while L1 pending (ordered)
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user(FIN)
        with self.assertRaises(Exception):
            api.approve(name)
        frappe.set_user("Administrator")

        frappe.set_user(mgr); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared(name, FIN) and _todo(name, FIN))
        frappe.set_user(FIN); api.approve(name); frappe.set_user("Administrator")
        frappe.set_user(HOF); api.approve(name); frappe.set_user("Administrator")
        frappe.set_user(CEO); api.approve(name); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        approvers = _actions(ar, "Approved")
        for u in (mgr, FIN, HOF, CEO):
            self.assertIn(u, approvers)
        # EC Approval Action has no level_no column and log_action never populates
        # request_level - assert FIN acted SECOND in the ordered Approved sequence
        # (fresh-site portability fix, 2026-07-12; original intent: FIN owns L2)
        acts = frappe.get_all("EC Approval Action",
                              filters={"approval_request": ar, "action": "Approved"},
                              fields=["actor"], order_by="seq asc")
        self.assertEqual(acts[1].actor, FIN)

    def test_missing_manager_blocked(self):
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)
        name = _draft(orphan)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_validation(self):
        mgr = _user(PFX + "vmgr@example.com")
        req = _user(PFX + "vreq@example.com"); _employee(req, reports_to=_employee(mgr))
        for over in ({"payment_amount": 0}, {"request_attachment": ""}, {"department": "NOPE"},
                     {"payment_term": "Other", "payment_term_other": ""},
                     {"estimated_purchase_date": "2026-09-10", "estimated_delivery_date": "2026-09-01"}):
            frappe.set_user(req)
            # invalid Link values (e.g. department NOPE) may already raise at draft
            # save on strict stacks - the rejection may come from either step
            with self.assertRaises(Exception):
                n = _draft(req, **over)
                frappe.set_user(req)
                api.submit_request(n)
            frappe.set_user("Administrator")
