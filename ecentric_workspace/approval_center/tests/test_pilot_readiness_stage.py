# Copyright (c) 2026, eCentric and contributors
"""Stage-aware UAT pilot readiness (fix/scts-requester-readiness-stage-awareness). Runs on the
bench: bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_pilot_readiness_stage
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import pilot
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

AR = "EC Approval Request"
SETTINGS = "EC Digital Signature Provider Settings"
BD, AT = "EC Payment Request", "PAYMENT_REQUEST"


def _scts_profile(requester=1):
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    name = frappe.db.get_value("EC Digital Signature Profile", "ZZESN_PAYR", "name")
    frappe.db.set_value("EC Digital Signature Profile", name,
                        {"provider": "SCTS", "environment": "UAT",
                         "approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": requester,
                         "workflow_definition_id": "WF", "document_type_id": "DT",
                         "company_id": "C", "department_id": "D", "document_template_id": "T"})


def _scts_settings(integration=1, doc_creation=0, signing=0, allow=None):
    nm = frappe.db.get_value(SETTINGS, {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "base_url_allowlist": "scts.uat.local",
            "username": "erp-bot", "integration_enabled": integration,
            "allow_document_creation": doc_creation, "allow_signing": signing,
            "allow_production_signing": 0, "allow_callback": 0, "allow_bulk_signing": 0,
            "allowed_signing_users": allow or ""}
    if nm:
        d = frappe.get_doc(SETTINGS, nm); d.update(vals); d.save(ignore_permissions=True)
    else:
        frappe.get_doc(dict({"doctype": SETTINGS, "provider": "SCTS", "environment": "UAT"},
                            **vals)).insert(ignore_permissions=True)


class TestPilotReadinessStage(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def _requester_pending(self, tag):
        _scts_profile(requester=1)
        h = fx.full_stack(fx.PFX + tag + "r@x.com", fx.PFX + tag + "m@x.com")
        # ensure the request is in requester pre-approval state
        frappe.db.set_value(AR, h["ar"], {"requester_signature_status": "Pending", "current_level": 0})
        _scts_settings(integration=1, doc_creation=0, signing=0, allow=h["requester"])
        frappe.get_doc("User", frappe.session.user)  # SM caller = Administrator
        return h

    def test_requester_stage_uses_requester_checks_only(self):
        h = self._requester_pending("st1")
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertEqual(out["actor_type"], "Requester")
        self.assertEqual(out["stage"], "Requester Pre-Approval")
        self.assertIn("requester_stage_detected", out["checks"])
        # NO approver/level blockers surfaced
        for k in ("active_approver_in_uat_allowlist", "exact_active_profile_for_approval_type",
                  "active_approver_resolved", "level_resolved"):
            self.assertNotIn(k, out["blocking_items"])

    def test_profile_resolves_while_signing_off(self):
        h = self._requester_pending("st2")  # signing OFF
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertTrue(out["checks"]["enabled_profile_exact"]["ok"])
        self.assertTrue(out["checks"]["requester_signature_required"]["ok"])
        self.assertTrue(out["checks"]["current_level_zero"]["ok"])
        self.assertTrue(out["checks"]["no_level_one_actionability"]["ok"])

    def test_gates_off_remain_blockers(self):
        h = self._requester_pending("st3")  # doc_creation + signing OFF
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertIn("document_creation_enabled", out["blocking_items"])
        self.assertIn("signing_enabled", out["blocking_items"])
        self.assertFalse(out["ready"])

    def test_requester_allowlist_and_mapping_checks(self):
        h = self._requester_pending("st4")
        fx.ensure_mapping(h["requester"])   # verified mapping
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertTrue(out["checks"]["requester_in_uat_allowlist"]["ok"])
        self.assertTrue(out["checks"]["requester_mapping_active_verified"]["ok"])

    def test_missing_requester_mapping_fails_closed(self):
        h = self._requester_pending("st5")
        frappe.db.delete("EC SCTS User Mapping", {"frappe_user": h["requester"]})
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertFalse(out["checks"]["requester_mapping_active_verified"]["ok"])
        self.assertIn("requester_mapping_active_verified", out["blocking_items"])

    def test_package_checks_distinct(self):
        h = self._requester_pending("st6")
        out = pilot.uat_pilot_readiness(h["biz"])
        for k in ("package_exists", "package_locked", "package_hash_valid",
                  "requester_placement_complete"):
            self.assertIn(k, out["checks"])

    def test_approval_stage_unchanged(self):
        # a non-requester profile -> approver stage, existing keys present
        _scts_profile(requester=0)
        _scts_settings(integration=1, doc_creation=1, signing=1)
        h = fx.full_stack(fx.PFX + "st7r@x.com", fx.PFX + "st7m@x.com")
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertEqual(out["actor_type"], "Approval Level")
        self.assertIn("exact_active_profile_for_approval_type", out["checks"])
