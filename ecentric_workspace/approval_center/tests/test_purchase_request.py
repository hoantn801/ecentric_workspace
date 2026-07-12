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

PFX = "ZZPUR_"
FIN = PFX + "fin@example.com"
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
    if not frappe.db.exists("Company", "ZZPUR Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZPUR Co", "abbr": "ZZPURC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZPUR Co"


def _dept():
    if not frappe.db.exists("Department", {"department_name": "ZZPUR Dept"}):
        return frappe.get_doc({"doctype": "Department", "department_name": "ZZPUR Dept",
                               "company": _company()}).insert(ignore_permissions=True).name
    return frappe.db.get_value("Department", {"department_name": "ZZPUR Dept"}, "name")


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
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(FIN); _user(HOF); _user(CEO)
    psetup.setup_purchase_request_v1(finance=[FIN], hof=[HOF], ceo=[CEO], apply=1)
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
        self.assertEqual(frappe.db.get_value("EC Approval Action",
                         {"approval_request": ar, "level_no": 2, "action": "Approved"}, "actor"), FIN)

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
            n = _draft(req, **over)
            frappe.set_user(req)
            with self.assertRaises(Exception):
                api.submit_request(n)
            frappe.set_user("Administrator")
