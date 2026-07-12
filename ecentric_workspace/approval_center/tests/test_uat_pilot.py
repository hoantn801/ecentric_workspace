# Copyright (c) 2026, eCentric and contributors
"""UAT pilot readiness + opt-in probe (S2B-C1 + actor-separation fix). Readiness is
SM-only, read-only; mapping/signature/allowlist checks target the ACTIVE APPROVER, not the
SM caller. apply=1 requires caller == active approver (role alone is never a bypass).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_uat_pilot
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import pilot
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

SETTINGS = "EC Digital Signature Provider Settings"


def _grant_sm(user):
    frappe.get_doc("User", user).add_roles("System Manager")


def _ready_stack(reqmail, mgrmail):
    h = fx.full_stack(fx.PFX + reqmail, fx.PFX + mgrmail)
    name = frappe.db.get_value(SETTINGS, {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "username": "erp-bot",
            "integration_enabled": 1, "allow_document_creation": 1, "allow_signing": 1,
            "allow_production_signing": 0, "allow_callback": 0, "allow_bulk_signing": 0,
            "allowed_signing_users": "\n".join(h["approvers"])}
    if name:
        d = frappe.get_doc(SETTINGS, name); d.update(vals); d.save(ignore_permissions=True)
    else:
        frappe.get_doc(dict({"doctype": SETTINGS, "provider": "SCTS",
                             "environment": "UAT"}, **vals)).insert(ignore_permissions=True)
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR", {
        "provider": "SCTS", "workflow_definition_id": "WF9", "document_type_id": "DT3",
        "company_id": "C1", "department_id": "D2", "document_template_id": "TPL7"})
    _grant_sm(h["mgr"])
    return h


def _settings_name():
    return frappe.db.get_value(SETTINGS, {"provider": "SCTS", "environment": "UAT"}, "name")


class TestUatPilotReadiness(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_all_green_ready(self):
        h = _ready_stack("u1r", "u1m")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(out["ready"], "blocking: %s" % out["blocking_items"])
        self.assertEqual(out["caller_user"], h["mgr"])
        self.assertEqual(out["active_approver"], h["mgr"])

    def test_production_signing_enabled_blocks(self):
        h = _ready_stack("u2r", "u2m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allow_production_signing", 1)
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("production_signing_disabled", out["blocking_items"])

    def test_signing_gate_disabled_blocks(self):
        h = _ready_stack("u3r", "u3m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allow_signing", 0)
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("signing_enabled", out["blocking_items"])

    def test_active_approver_not_allowlisted_blocks(self):
        h = _ready_stack("u4r", "u4m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allowed_signing_users", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("active_approver_in_uat_allowlist", out["blocking_items"])

    def test_missing_base_url_blocks(self):
        h = _ready_stack("u5r", "u5m")
        frappe.db.set_value(SETTINGS, _settings_name(), "base_url", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("base_url_configured", out["blocking_items"])

    def test_sm_can_inspect_other_approver_without_being_signer(self):
        # CEO is a System Manager but NOT the current (level-1) approver (mgr is).
        h = _ready_stack("u6r", "u6m")
        _grant_sm(fx.CEO)
        frappe.set_user(fx.CEO)
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(out["caller_user"], fx.CEO)
        self.assertEqual(out["active_approver"], h["mgr"])  # resolved from persisted state
        self.assertIn("caller_is_active_approver", out["warnings"])  # warning, not blocker
        # mapping/allowlist were evaluated for the ACTIVE APPROVER (mgr), so they pass
        self.assertTrue(out["checks"]["approver_exactly_one_active_mapping"]["ok"])
        self.assertTrue(out["checks"]["active_approver_in_uat_allowlist"]["ok"])

    def test_readiness_uses_active_approver_mapping_not_caller(self):
        # The SM caller (CEO) has NO mapping; the active approver (mgr) does.
        h = _ready_stack("u7r", "u7m")
        _grant_sm(fx.CEO)
        frappe.db.delete("EC SCTS User Mapping", {"frappe_user": fx.CEO})
        frappe.set_user(fx.CEO)
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        # mapping check is TRUE because it evaluates the approver (mgr), not the caller
        self.assertTrue(out["checks"]["approver_exactly_one_active_mapping"]["ok"])

    def test_non_system_manager_blocked(self):
        h = _ready_stack("u8r", "u8m")
        frappe.set_user(h["requester"])
        with self.assertRaises(frappe.PermissionError):
            pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")


class TestUatPilotProbe(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_apply0_makes_no_external_write(self):
        h = _ready_stack("q1r", "q1m")
        frappe.set_user(h["mgr"])
        from ecentric_workspace.approval_center.esign import tasks

        def spy(settings):
            raise AssertionError("no adapter should be built in apply=0")

        with patch.object(tasks, "get_adapter", spy):
            out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=0)
        frappe.set_user("Administrator")
        self.assertFalse(out["applied"])
        self.assertEqual(out["mode"], "preview")
        self.assertEqual(out["payload_preview"]["credentials"], "<never included>")

    def test_apply1_blocked_when_sm_not_active_approver(self):
        h = _ready_stack("q2r", "q2m")
        _grant_sm(fx.CEO)  # SM, but not the level-1 approver; PR is TEST-named by fixture
        frappe.set_user(fx.CEO)
        out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        frappe.set_user("Administrator")
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "caller_not_active_approver")

    def test_administrator_has_no_bypass_apply1(self):
        h = _ready_stack("q3r", "q3m")
        # Administrator is SM but not the active approver -> still blocked.
        frappe.set_user("Administrator")
        out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "caller_not_active_approver")

    def test_apply1_passes_when_caller_is_active_approver(self):
        h = _ready_stack("q4r", "q4m")  # fixture reason "esign test" -> UAT/TEST-named
        frappe.set_user(h["mgr"])  # mgr = SM + active approver + mapped + allowlisted
        out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        frappe.set_user("Administrator")
        self.assertTrue(out["applied"])
        self.assertTrue(out["signature_request"])
        self.assertEqual(out["active_approver"], h["mgr"])

    def test_apply1_non_void_named_rejected(self):
        h = _ready_stack("q5r", "q5m")
        # remove all UAT/VOID/TEST markers from name-relevant fields
        frappe.db.set_value("EC Payment Request", h["biz"],
                            {"request_title": "Real payment", "reason": "Quarterly rent"})
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        frappe.set_user("Administrator")

    def test_probe_requires_system_manager(self):
        h = _ready_stack("q6r", "q6m")
        frappe.set_user(h["requester"])
        with self.assertRaises(frappe.PermissionError):
            pilot.run_scts_uat_pilot_probe(h["biz"], apply=0)
        frappe.set_user("Administrator")
