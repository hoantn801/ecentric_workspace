# Copyright (c) 2026, eCentric and contributors
"""B3.1 read-API tests: permission scope + capability flags.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b3_api
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import ai_topup as api

PFX = "ZZB3_"


def _user(email, roles=("Employee",), enabled=1, utype="System User"):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": utype, "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        if utype == "System User":
            u.add_roles(*roles)
    return email


def _tool():
    if not frappe.db.exists("EC AI Tool", "ZZB3 Tool"):
        frappe.get_doc({"doctype": "EC AI Tool", "tool_name": "ZZB3 Tool"}).insert(ignore_permissions=True)
    return "ZZB3 Tool"


def _draft(owner):
    return frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                           "ai_tool": _tool(), "proposed_account_email": "d@example.com",
                           "proposed_account_manager": _user("zzb3_pm@example.com"),
                           "requested_by": owner}).insert(ignore_permissions=True)


class TestB3ReadAPI(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_form_options(self):
        opt = api.get_form_options()
        self.assertEqual(opt["account_modes"], ["Existing Account", "New Account"])
        self.assertIn("Top-up", opt["request_types"])
        self.assertIn("Monthly", opt["billing_cycles"])

    def test_active_user_search_hides_admin_for_non_sm(self):
        _user("zzb3_plain@example.com")
        frappe.set_user("zzb3_plain@example.com")
        rows = api.search_active_users(query="Admin")
        self.assertFalse(any(r["value"] == "Administrator" for r in rows))

    def test_my_requests_scoped_to_owner(self):
        a = _user("zzb3_a@example.com"); b = _user("zzb3_b@example.com")
        da = _draft(a)
        frappe.set_user(b)
        names = [r["name"] for r in api.list_my_requests()["rows"]]
        self.assertNotIn(da.name, names)
        frappe.set_user(a)
        self.assertIn(da.name, [r["name"] for r in api.list_my_requests()["rows"]])

    def test_detail_scope_denies_unrelated(self):
        a = _user("zzb3_a@example.com"); b = _user("zzb3_b@example.com")
        da = _draft(a)
        frappe.set_user(b)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.get_request_detail(da.name)

    def test_capabilities_for_draft_owner(self):
        a = _user("zzb3_a@example.com")
        da = _draft(a)
        frappe.set_user(a)
        cap = api.get_request_detail(da.name)["capabilities"]
        self.assertTrue(cap["can_submit"] and cap["can_edit"])
        self.assertFalse(cap["can_approve"])

    def test_fulfillment_queue_requires_eligibility(self):
        p = _user("zzb3_plain2@example.com")
        frappe.set_user(p)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.list_fulfillment_queue(section="unclaimed")

    def test_bootstrap_tabs(self):
        a = _user("zzb3_a@example.com")
        frappe.set_user(a)
        boot = api.get_bootstrap()
        self.assertTrue(boot["tabs"]["create"] and boot["tabs"]["my_requests"])
        self.assertIn("manager_resolvable", boot["context"])
