# Copyright (c) 2026, eCentric and contributors
"""Asset Request (form #7) backend tests: Direct Manager resolver + block, chain
Direct Manager -> Operation -> fulfillment, complete summary required, quantity>0,
operation date set/updated (no default), setup/activation, page_sync.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_asset_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import asset_request as api
from ecentric_workspace.approval_center.asset_request import setup as arsetup
from ecentric_workspace.approval_center.asset_request import activation as aract
from ecentric_workspace.approval_center.asset_request import page_sync

PFX = "ZZAR_"
OP1 = PFX + "op1@example.com"
OP2 = PFX + "op2@example.com"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZAR Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZAR Co", "abbr": "ZZARC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZAR Co"


def _employee(user, manager_emp=None):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    doc = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                          "company": _company(), "status": "Active", "gender": "Other",
                          "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"})
    if manager_emp:
        doc.reports_to = manager_emp
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure():
    if not frappe.db.exists("EC Approval Type", "ASSET_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "ASSET_REQUEST",
                        "approval_title": "Asset Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(OP1); _user(OP2)
    arsetup.setup_asset_request_v1(operation_reviewers=[OP1, OP2], fulfillers=[OP1, OP2], apply=1)
    frappe.db.set_value("EC Approval Process", "ASSET_REQUEST-V1", "status", "Active")


def _req_with_mgr():
    mgr = _user(PFX + "mgr@example.com")
    mgr_emp = _employee(mgr)
    req = _user(PFX + "req@example.com")
    _employee(req, manager_emp=mgr_emp)
    return req, mgr


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "AR", "request_type": "Request new asset", "asset_type": "Laptop",
               "purpose_of_request": "New employee", "quantity": 1, "specifications": "16GB",
               "justification": "need it"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestAssetRequest(FrappeTestCase):
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

    def _open_todos(self, name):
        return frappe.get_all("ToDo", filters={"reference_type": api.BIZ, "reference_name": name,
                                               "status": "Open"}, pluck="allocated_to")

    def _submit(self):
        req, mgr = _req_with_mgr()
        name = _draft(req)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name, req, mgr

    def test_direct_manager_resolver_and_l1(self):
        name, req, mgr = self._submit()
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        l1 = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(mgr, l1)                               # Employee.reports_to -> manager
        self.assertIn(mgr, self._open_todos(name))

    def test_submit_blocked_when_no_manager(self):
        u = _user(PFX + "nomgr@example.com")
        _employee(u)                                         # no reports_to
        name = _draft(u)
        frappe.set_user(u)
        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            api.submit_request(name)
        frappe.set_user("Administrator")
        self.assertFalse(self._ar(name))
        self.assertIn("Quan ly truc tiep", str(cm.exception))

    def test_quantity_must_be_positive(self):
        req, mgr = _req_with_mgr()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "request_type": "Request new asset",
                "asset_type": "Laptop", "purpose_of_request": "New employee", "quantity": 0,
                "specifications": "s", "justification": "j"}))
        frappe.set_user("Administrator")

    def test_full_chain_manager_operation_fulfillment(self):
        name, req, mgr = self._submit()
        frappe.set_user(mgr)
        api.approve(name)                                    # L1 Direct Manager
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        frappe.set_user(OP1)
        api.approve(name)                                    # L2 Operation -> final -> fulfillment
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")

    def test_fulfillment_complete_summary_required_and_no_default_date(self):
        name, req, mgr = self._submit()
        frappe.set_user(mgr); api.approve(name)
        frappe.set_user(OP1); api.approve(name)
        # no default operation date injected
        self.assertFalse(frappe.db.get_value(api.BIZ, name, "operation_expected_completion_date"))
        frappe.set_user(OP1)
        api.set_operation_fields(name, operation_expected_completion_date="2026-09-15", operation_note="batch buy")
        api.claim_fulfillment(name)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.complete_fulfillment(name, payload=frappe.as_json({"fulfillment_summary": ""}))
        api.complete_fulfillment(name, payload=frappe.as_json(
            {"fulfillment_summary": "delivered", "asset_handover_note": "SN123"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Completed")
        self.assertEqual(str(frappe.db.get_value(api.BIZ, name, "operation_expected_completion_date")), "2026-09-15")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "asset_handover_note"), "SN123")
        self.assertFalse(self._open_todos(name))

    def test_setup_dry_apply_and_uat(self):
        rep = arsetup.setup_asset_request_v1(operation_reviewers=[OP1], fulfillers=[OP1], dry_run=1, apply=0)
        self.assertEqual(rep["mode"], "dry_run")
        r = aract.enable_asset_request_uat(apply=1)
        self.assertEqual(frappe.db.get_value("EC Approval Process", "ASSET_REQUEST-V1", "status"), "Active")
        self.assertEqual(frappe.db.get_value("EC Approval Type", "ASSET_REQUEST", "card_status"), "Coming Soon")
        self.assertEqual(r.get("result"), "UAT_ENABLED")

    def test_page_sync_idempotent_no_duplicate(self):
        if not frappe.db.exists("DocType", "Web Page"):
            self.skipTest("Web Page DocType not installed")
        slug = page_sync.NAME
        for n in list(frappe.get_all("Web Page", filters={"route": page_sync.ROUTE}, pluck="name")):
            frappe.delete_doc("Web Page", n, ignore_permissions=True, force=1)
        if frappe.db.exists("Web Page", slug):
            frappe.delete_doc("Web Page", slug, ignore_permissions=True, force=1)
        r1 = page_sync.sync()
        self.assertEqual(r1["action"], "created")
        self.assertEqual(page_sync.sync()["action"], "unchanged")           # re-run: no insert
        self.assertEqual(page_sync.sync(html="<div>x</div>")["action"], "updated")
        # simulate a partial-migrate page whose route drifted: a plain route lookup would miss,
        # but the slug-named page still exists -> re-sync must ADOPT+UPDATE it (no DuplicateEntryError)
        frappe.db.set_value("Web Page", r1["name"], "route", "zz-drift/" + slug)
        r2 = page_sync.sync()
        self.assertEqual(r2["action"], "updated")
        self.assertEqual(r2["name"], r1["name"])
        self.assertEqual(frappe.db.get_value("Web Page", r1["name"], "route"), page_sync.ROUTE)
        self.assertEqual(frappe.db.count("Web Page", {"name": r1["name"]}), 1)
