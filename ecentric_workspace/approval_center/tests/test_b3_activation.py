# Copyright (c) 2026, eCentric and contributors
"""B3.5 tests: page-sync idempotency + activation dry-run safety (never activates).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b3_activation
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.ai_topup import page_sync, activation


class TestPageSync(FrappeTestCase):
    def test_idempotent_create_then_update(self):
        r1 = page_sync.sync()
        r2 = page_sync.sync()
        self.assertIn(r1["action"], ("created", "updated"))
        self.assertEqual(r2["action"], "updated")
        self.assertEqual(len(frappe.get_all("Web Page", filters={"route": "approvals/ai-topup"})), 1)
        self.assertEqual(frappe.db.get_value("Web Page", {"route": "approvals/ai-topup"}, "published"), 1)


class TestActivation(FrappeTestCase):
    def test_dry_run_never_activates(self):
        rep = activation.activate_ai_topup(dry_run=1, apply=0)
        self.assertIn("checks", rep)
        self.assertIn(rep["result"].split()[0], ("BLOCKED", "DRY_RUN_OK"))
        # dry-run must not change card or process state
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", "AI_TOPUP", "card_status"), "Active")
        st = frappe.db.get_value("EC Approval Process", "AI_TOPUP-V1", "status")
        self.assertNotEqual(st, "Active")

    def test_blocked_when_not_ready_stops_before_apply(self):
        # retire any AI_TOPUP-V1 so validation fails, then apply must still be BLOCKED (no activation)
        if frappe.db.exists("EC Approval Process", "AI_TOPUP-V1"):
            frappe.db.set_value("EC Approval Process", "AI_TOPUP-V1", "status", "Retired")
        rep = activation.activate_ai_topup(dry_run=0, apply=1)
        self.assertTrue(rep["result"].startswith("BLOCKED"))
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", "AI_TOPUP", "card_status"), "Active")
