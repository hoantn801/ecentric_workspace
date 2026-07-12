# Copyright (c) 2026, eCentric and contributors
"""Backend-computed signing UI state (Phase 2). Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signing_ui_state
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import ui_state
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

_FORBIDDEN = ("password", "token", "authorization", "secret", "base64", "/private/files")


class TestSigningUiState(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_ready_to_sign_stage_when_active_package_no_dsr(self):
        h = fx.full_stack(fx.PFX + "us1r@example.com", fx.PFX + "us1m@example.com")
        frappe.set_user(h["mgr"])
        out = ui_state.signing_ui_state("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertIn(out["stage"], ("Ready to Sign", "Package Preparing"))
        self.assertEqual(out["stages"], list(ui_state.STAGES))

    def test_no_sensitive_fields_leaked(self):
        h = fx.full_stack(fx.PFX + "us2r@example.com", fx.PFX + "us2m@example.com")
        frappe.set_user(h["mgr"])
        out = ui_state.signing_ui_state("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        blob = frappe.as_json(out).lower()
        for bad in _FORBIDDEN:
            self.assertNotIn(bad, blob)

    def test_actions_include_refresh_and_audit(self):
        h = fx.full_stack(fx.PFX + "us3r@example.com", fx.PFX + "us3m@example.com")
        frappe.set_user(h["mgr"])
        out = ui_state.signing_ui_state("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("refresh_readiness", out["actions"])
        self.assertIn("view_audit", out["actions"])

    def test_readiness_echoed_from_service(self):
        h = fx.full_stack(fx.PFX + "us4r@example.com", fx.PFX + "us4m@example.com")
        frappe.set_user(h["mgr"])
        out = ui_state.signing_ui_state("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("readiness", out)
        self.assertEqual(out["can_sign"], bool(out["readiness"].get("ready")))

    def test_requester_can_view_state(self):
        h = fx.full_stack(fx.PFX + "us5r@example.com", fx.PFX + "us5m@example.com")
        frappe.set_user(h["requester"])
        out = ui_state.signing_ui_state("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertFalse(out["can_sign"])   # requester is not the approver
