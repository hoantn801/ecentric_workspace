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
from ecentric_workspace.approval_center.daily_target import page_sync
from ecentric_workspace.approval_center.daily_target import service as dtsvc
from ecentric_workspace.approval_center.patches import p019_hide_daily_target_project_card as p019

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


class TestDailyTargetProjectCardCleanup(FrappeTestCase):
    """Cleanup A: hide the duplicate 'Daily Target Setting - Project Level' catalog card without
    touching the process, the main card, or request data."""

    def test_p019_disables_duplicate_card_only(self):
        # ensure both catalog rows exist
        for code, title, status in (("DAILY_TARGET", "Daily Target Setting", "Active"),
                                    ("DAILY_TARGET_PROJECT", "Daily Target Setting - Project Level", "Coming Soon")):
            if not frappe.db.exists("EC Approval Type", code):
                frappe.get_doc({"doctype": "EC Approval Type", "approval_code": code, "approval_title": title,
                                "card_status": status, "process_status": "Discovery"}).insert(ignore_permissions=True)
        frappe.db.set_value("EC Approval Type", "DAILY_TARGET", "card_status", "Active")
        _ensure()   # creates DAILY_TARGET_PROJECT-V1 process
        p019.execute()
        # duplicate card hidden
        self.assertEqual(frappe.db.get_value("EC Approval Type", "DAILY_TARGET_PROJECT", "card_status"), "Disabled")
        # main card untouched; process intact; scope mapping unchanged
        self.assertEqual(frappe.db.get_value("EC Approval Type", "DAILY_TARGET", "card_status"), "Active")
        self.assertTrue(frappe.db.exists("EC Approval Process", dtsvc.PROCESS_PROJECT))
        self.assertEqual(dtsvc.process_for_scope("Project level"), dtsvc.PROCESS_PROJECT)
        # idempotent re-run
        p019.execute()
        self.assertEqual(frappe.db.get_value("EC Approval Type", "DAILY_TARGET_PROJECT", "card_status"), "Disabled")
