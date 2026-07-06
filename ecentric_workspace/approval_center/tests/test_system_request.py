# Copyright (c) 2026, eCentric and contributors
"""System Request (form #3) backend tests: draft/submit/validation, Data Review Any One
approval, fulfillment claim+complete (summary required), request-info+resubmit, ToDo
lifecycle, timeline, admin override, setup/activation apply, page_sync.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_system_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import system_request as api
from ecentric_workspace.approval_center.system_request import setup as drsetup
from ecentric_workspace.approval_center.system_request import activation as dract
from ecentric_workspace.approval_center.system_request import page_sync

PFX = "ZZSR_"
REV1 = PFX + "rev1@example.com"
REV2 = PFX + "rev2@example.com"


def _user(email, roles=("Employee",), enabled=1):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZDR Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZDR Co", "abbr": "ZZDRC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZDR Co"


def _employee(user):
    existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "SYSTEM_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "SYSTEM_REQUEST",
                        "approval_title": "System Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(REV1); _user(REV2)
    drsetup.setup_system_request_v1(review_approvers=[REV1, REV2], fulfillers=[REV1, REV2], apply=1)
    frappe.db.set_value("EC Approval Process", "SYSTEM_REQUEST-V1", "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "SR", "request_type": "Access, permission", "description": "need access",
               "priority": "High", "requester_expected_resolution_date": "2026-08-10"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestSystemRequest(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def setUp(self):
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def _open_todos(self, name, user=None):
        f = {"reference_type": api.BIZ, "reference_name": name, "status": "Open"}
        if user:
            f["allocated_to"] = user
        return frappe.get_all("ToDo", filters=f, pluck="allocated_to")

    def _submit(self):
        req = _requester()
        name = _draft(req)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name, req

    def test_save_draft_and_submit(self):
        name, req = self._submit()
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        todos = self._open_todos(name)
        self.assertTrue(REV1 in todos or REV2 in todos)     # Data Review ToDo(s)

    def test_submit_blocked_missing_required(self):
        req = _requester()
        name = _draft(req, priority="")
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_any_one_approval_advances_to_fulfillment(self):
        name, req = self._submit()
        frappe.set_user(REV1)
        api.approve(name, comment="ok")                     # Any One -> level approved -> final
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")
        # REV2's redundant pending approver row is Skipped (Any One)
        st = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="status")
        self.assertIn("Approved", st)
        # fulfillment ToDos assigned
        self.assertTrue(self._open_todos(name))

    def test_fulfillment_claim_complete_summary_required(self):
        name, req = self._submit()
        frappe.set_user(REV1)
        api.approve(name)
        # claim
        frappe.set_user(REV1)
        api.claim_fulfillment(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "In Progress")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_owner"), REV1)
        # complete requires summary
        frappe.set_user(REV1)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.complete_fulfillment(name, payload=frappe.as_json({"fulfillment_summary": ""}))
        api.complete_fulfillment(name, payload=frappe.as_json(
            {"fulfillment_summary": "done", "output_link": "https://x"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Completed")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "completed_by"), REV1)
        self.assertFalse(self._open_todos(name))            # ToDos closed on completion

    def test_request_information_and_resubmit(self):
        name, req = self._submit()
        frappe.set_user(REV1)
        api.request_information(name, comment="cần thêm chi tiết")
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Information Required")
        self.assertFalse(self._open_todos(name))            # approver ToDo paused
        frappe.set_user(req)
        api.resubmit(name, payload=frappe.as_json({"description": "chi tiết hơn"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertTrue(self._open_todos(name))             # Data Review ToDo recreated

    def test_timeline_records_actions(self):
        name, req = self._submit()
        frappe.set_user(REV1)
        api.approve(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        acts = frappe.get_all("EC Approval Action", filters={"approval_request": ar}, pluck="action")
        self.assertIn("Submitted", acts)
        self.assertIn("Approved", acts)

    def test_admin_override(self):
        name, req = self._submit()
        frappe.set_user("Administrator")                    # System Manager
        api.admin_approve_current_level(name, reason="urgent")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")

    def test_setup_dry_run_vs_apply(self):
        rep = drsetup.setup_system_request_v1(review_approvers=[REV1], fulfillers=[REV1], dry_run=1, apply=0)
        self.assertEqual(rep["mode"], "dry_run")
        rep2 = drsetup.setup_system_request_v1(review_approvers=[REV1], fulfillers=[REV1], apply=1)
        self.assertEqual(rep2["mode"], "apply")
        self.assertTrue(frappe.db.exists("EC Approval Process", "SYSTEM_REQUEST-V1"))

    def test_enable_uat_keeps_card_inactive(self):
        r = dract.enable_system_request_uat(apply=1)
        self.assertEqual(frappe.db.get_value("EC Approval Process", "SYSTEM_REQUEST-V1", "status"), "Active")
        self.assertEqual(frappe.db.get_value("EC Approval Type", "SYSTEM_REQUEST", "card_status"), "Coming Soon")
        self.assertEqual(r.get("result"), "UAT_ENABLED")

    def test_operation_expected_date_set_and_no_default(self):
        name, req = self._submit()
        # no default 3-day date injected at submit
        self.assertFalse(frappe.db.get_value(api.BIZ, name, "operation_expected_completion_date"))
        # a current Operation reviewer records it
        frappe.set_user(REV1)
        api.set_operation_fields(name, operation_expected_completion_date="2026-09-01", operation_note="batch")
        frappe.set_user("Administrator")
        self.assertEqual(str(frappe.db.get_value(api.BIZ, name, "operation_expected_completion_date")), "2026-09-01")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "operation_note"), "batch")

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
