# Copyright (c) 2026, eCentric and contributors
"""B3.5 tests: page-sync idempotency + split UAT-enable / publish activation.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b3_activation
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.ai_topup import page_sync, setup, activation

PROCESS = "AI_TOPUP-V1"
TYPE = "AI_TOPUP"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _full_setup():
    op = [_user("zzb35_op1@example.com"), _user("zzb35_op2@example.com")]
    fin = [_user("zzb35_fin1@example.com"), _user("zzb35_fin2@example.com")]
    setup.setup_ai_topup_v1(op, op, fin, dry_run=0, apply=1)
    page_sync.sync()


def _reset():
    if frappe.db.exists("EC Approval Process", PROCESS):
        frappe.db.set_value("EC Approval Process", PROCESS, "status", "Draft")
    if frappe.db.exists("EC Approval Type", TYPE):
        frappe.db.set_value("EC Approval Type", TYPE, {"card_status": "Coming Soon", "route": ""})


class TestPageSync(FrappeTestCase):
    def test_idempotent_create_then_update(self):
        r1 = page_sync.sync()
        r2 = page_sync.sync()
        self.assertIn(r1["action"], ("created", "updated"))
        self.assertEqual(r2["action"], "updated")
        self.assertEqual(len(frappe.get_all("Web Page", filters={"route": "approvals/ai-topup"})), 1)
        self.assertEqual(frappe.db.get_value("Web Page", {"route": "approvals/ai-topup"}, "published"), 1)


class TestSplitActivation(FrappeTestCase):
    def setUp(self):
        _full_setup(); _reset()

    def tearDown(self):
        _reset()

    def test_uat_enable_dry_run_no_mutate(self):
        rep = activation.enable_ai_topup_uat(dry_run=1, apply=0)
        self.assertTrue(rep["result"].startswith("DRY_RUN_OK"))
        self.assertEqual(frappe.db.get_value("EC Approval Process", PROCESS, "status"), "Draft")

    def test_uat_enable_apply_activates_process_card_inactive(self):
        rep = activation.enable_ai_topup_uat(dry_run=0, apply=1)
        self.assertTrue(rep["result"].startswith("UAT_ENABLED"))
        self.assertEqual(frappe.db.get_value("EC Approval Process", PROCESS, "status"), "Active")
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", TYPE, "card_status"), "Active")  # card hidden
        # audit comment on process
        self.assertTrue(frappe.get_all("Comment", filters={
            "reference_doctype": "EC Approval Process", "reference_name": PROCESS, "comment_type": "Info"}))

    def test_uat_enable_idempotent(self):
        activation.enable_ai_topup_uat(dry_run=0, apply=1)
        rep = activation.enable_ai_topup_uat(dry_run=0, apply=1)
        self.assertTrue(rep["result"].startswith("UAT_ENABLED"))
        self.assertEqual(frappe.db.get_value("EC Approval Process", PROCESS, "status"), "Active")

    def test_publish_dry_run_no_mutate(self):
        activation.enable_ai_topup_uat(dry_run=0, apply=1)
        rep = activation.publish_ai_topup_after_uat(dry_run=1, apply=0)
        self.assertTrue(rep["result"].startswith("DRY_RUN_OK"))
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", TYPE, "card_status"), "Active")

    def test_publish_blocked_if_process_not_active(self):
        rep = activation.publish_ai_topup_after_uat(dry_run=0, apply=1)   # process still Draft
        self.assertTrue(rep["result"].startswith("BLOCKED"))
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", TYPE, "card_status"), "Active")

    def test_publish_apply_activates_card_and_idempotent(self):
        activation.enable_ai_topup_uat(dry_run=0, apply=1)
        rep = activation.publish_ai_topup_after_uat(dry_run=0, apply=1)
        self.assertTrue(rep["result"].startswith("PUBLISHED"))
        self.assertEqual(frappe.db.get_value("EC Approval Type", TYPE, "card_status"), "Active")
        self.assertEqual(frappe.db.get_value("EC Approval Type", TYPE, "route"), "/approvals/ai-topup")
        self.assertTrue(frappe.get_all("Comment", filters={
            "reference_doctype": "EC Approval Type", "reference_name": TYPE, "comment_type": "Info"}))
        rep2 = activation.publish_ai_topup_after_uat(dry_run=0, apply=1)  # idempotent
        self.assertTrue(rep2["result"].startswith("PUBLISHED"))

    def test_no_conflicting_active_process_blocks(self):
        activation.enable_ai_topup_uat(dry_run=0, apply=1)
        other = frappe.get_doc({"doctype": "EC Approval Process", "process_code": "ZZB35_OTHER",
                                "title": "x", "approval_type": TYPE, "status": "Draft"}).insert(ignore_permissions=True)
        # can't have two Active for one type at DB level; force via db to simulate a conflict row
        frappe.db.set_value("EC Approval Process", other.name,
                            {"status": "Active", "active_process_key": TYPE + "_CONFLICT"})
        rep = activation.publish_ai_topup_after_uat(dry_run=1, apply=0)
        self.assertTrue(any(c["check"].startswith("no OTHER Active") and c["status"] == "FAIL"
                            for c in rep["checks"]))
