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


class TestB3WriteAndSafeguards(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_save_draft_owner_and_capabilities(self):
        a = _user("zzb3_wa@example.com")
        frappe.set_user(a)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "n@example.com",
            "proposed_account_manager": _user("zzb3_wpm@example.com")}))
        self.assertTrue(res["name"])
        self.assertTrue(res["capabilities"]["can_submit"] and res["capabilities"]["can_edit"])
        self.assertEqual(frappe.db.get_value(api.BIZ, res["name"], "requested_by"), a)

    def test_save_draft_denies_other_owner(self):
        a = _user("zzb3_wa@example.com"); b = _user("zzb3_wb@example.com")
        doc = _draft(a)
        frappe.set_user(b)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.save_draft(name=doc.name, payload="{}")

    def test_page_size_capped(self):
        self.assertEqual(api.MAX_PAGE, 50)
        a = _user("zzb3_wa@example.com"); frappe.set_user(a)
        res = api.list_my_requests(page_length=1000)   # must not error; capped internally
        self.assertLessEqual(len(res["rows"]), 50)

    def test_active_user_minimal_shape(self):
        frappe.set_user("Administrator")
        rows = api.search_active_users(query="a")
        if rows:
            self.assertEqual(set(rows[0].keys()), {"value", "email", "label"})


def _active_proc(l1_user, l2_users):
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "AI_TOPUP", "status": "Active"}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Retired")
    code = "ZZB3A_" + frappe.generate_hash(length=5)
    p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                        "approval_type": "AI_TOPUP", "status": "Draft"}).insert(ignore_permissions=True)
    l1 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 1,
                         "level_name": "Manager", "approval_mode": "Any One"})
    l1.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": l1_user})
    l1.insert(ignore_permissions=True)
    l2 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 2,
                         "level_name": "Finance Review", "approval_mode": "Any One"})
    for u in l2_users:
        l2.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": u})
    l2.insert(ignore_permissions=True)
    p.status = "Active"; p.save(ignore_permissions=True)
    return p.name


def _submit_as(requester, l1_user, l2_users):
    doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                          "ai_tool": _tool(), "proposed_account_email": "s@example.com",
                          "proposed_account_manager": _user("zzb3_spm@example.com"),
                          "requested_by": requester}).insert(ignore_permissions=True)
    frappe.set_user(requester)
    api.submit_request(doc.name)
    frappe.set_user("Administrator")
    return doc.name


class TestB3Actions(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_my_approvals_scope_and_actions(self):
        a = _user("zzb3_apr@example.com"); other = _user("zzb3_oth@example.com")
        req = _user("zzb3_req@example.com")
        _active_proc(a, ["zzb3_fin@example.com"])
        name = _submit_as(req, a, ["zzb3_fin@example.com"])
        frappe.set_user(a)
        pend = api.list_my_approvals(section="pending")["rows"]
        self.assertTrue(any(r["name"] == name for r in pend))
        frappe.set_user(other)
        self.assertFalse(any(r["name"] == name for r in api.list_my_approvals(section="pending")["rows"]))

    def test_reject_reason_required_and_unrelated_denied(self):
        a = _user("zzb3_apr@example.com"); other = _user("zzb3_oth@example.com"); req = _user("zzb3_req@example.com")
        _active_proc(a, ["zzb3_fin@example.com"])
        name = _submit_as(req, a, ["zzb3_fin@example.com"])
        frappe.set_user(a)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.reject(name, comment="")             # reason required (engine)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.request_information(name, comment="")  # comment required (engine)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.approve(name)                          # not a pending approver

    def test_approve_then_duplicate_blocked(self):
        a = _user("zzb3_apr@example.com"); req = _user("zzb3_req@example.com")
        _active_proc(a, [a])   # a is approver at both levels (Any One)
        name = _submit_as(req, a, [a])
        frappe.set_user(a)
        api.approve(name)                              # L1 -> advances to L2
        api.approve(name)                              # L2 -> Approved
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.approve(name)                          # terminal -> blocked

    def test_cancel_draft_and_capability(self):
        req = _user("zzb3_req@example.com"); other = _user("zzb3_oth@example.com")
        doc = _draft(req)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.cancel(doc.name, reason="x")
        frappe.set_user(req)
        res = api.cancel(doc.name, reason="không cần nữa")
        self.assertTrue(res.get("deleted"))
        self.assertFalse(frappe.db.exists(api.BIZ, doc.name))
