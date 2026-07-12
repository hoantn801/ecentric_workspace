# Copyright (c) 2026, eCentric and contributors
"""UAT pilot readiness + opt-in probe (S2B-C1). Readiness is SM-only, read-only; the
probe never writes with apply=0 and is heavily gated for apply=1.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_uat_pilot
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import pilot
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

SETTINGS = "EC Digital Signature Provider Settings"


def _grant_sm(user):
    u = frappe.get_doc("User", user)
    u.add_roles("System Manager")


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
        frappe.set_user(h["mgr"])  # mgr is SM + active approver + mapped + allowlisted
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(out["ready"], "blocking: %s" % out["blocking_items"])

    def test_production_signing_enabled_blocks(self):
        h = _ready_stack("u2r", "u2m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allow_production_signing", 1)
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertFalse(out["ready"])
        self.assertIn("production_signing_disabled", out["blocking_items"])

    def test_signing_gate_disabled_blocks(self):
        h = _ready_stack("u3r", "u3m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allow_signing", 0)
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("signing_enabled", out["blocking_items"])

    def test_not_allowlisted_blocks(self):
        h = _ready_stack("u4r", "u4m")
        frappe.db.set_value(SETTINGS, _settings_name(), "allowed_signing_users", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("user_in_uat_allowlist", out["blocking_items"])

    def test_missing_base_url_blocks(self):
        h = _ready_stack("u5r", "u5m")
        frappe.db.set_value(SETTINGS, _settings_name(), "base_url", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("base_url_configured", out["blocking_items"])

    def test_wrong_approver_blocks(self):
        h = _ready_stack("u6r", "u6m")
        _grant_sm(fx.CEO)  # CEO is SM but NOT the current (level-1) approver
        frappe.set_user(fx.CEO)
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("current_user_is_active_approver", out["blocking_items"])

    def test_non_system_manager_blocked(self):
        h = _ready_stack("u7r", "u7m")
        frappe.set_user(h["requester"])  # plain Employee
        with self.assertRaises(frappe.PermissionError):
            pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")


class TestUatPilotProbe(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_apply0_makes_no_external_write(self):
        h = _ready_stack("p1r", "p1m")
        frappe.set_user(h["mgr"])
        calls = {"n": 0}
        from ecentric_workspace.approval_center.esign import tasks

        def spy(settings):
            calls["n"] += 1
            raise AssertionError("no adapter should be built in apply=0")

        with patch.object(tasks, "get_adapter", spy):
            out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=0)
        frappe.set_user("Administrator")
        self.assertFalse(out["applied"])
        self.assertEqual(out["mode"], "preview")
        self.assertEqual(calls["n"], 0)
        self.assertIn("credentials", out["payload_preview"])
        self.assertEqual(out["payload_preview"]["credentials"], "<never included>")

    def test_apply1_non_void_named_rejected(self):
        h = _ready_stack("p2r", "p2m")  # PR name/title is not UAT/VOID
        frappe.db.set_value("EC Payment Request", h["biz"], "request_title", "Real payment")
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        frappe.set_user("Administrator")

    def test_apply1_blocked_when_readiness_incomplete(self):
        h = _ready_stack("p3r", "p3m")
        frappe.db.set_value("EC Payment Request", h["biz"], "request_title", "VOID uat test")
        frappe.db.set_value(SETTINGS, _settings_name(), "allow_signing", 0)  # not ready
        frappe.set_user(h["mgr"])
        out = pilot.run_scts_uat_pilot_probe(h["biz"], apply=1)
        frappe.set_user("Administrator")
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "readiness_incomplete")

    def test_probe_requires_system_manager(self):
        h = _ready_stack("p4r", "p4m")
        frappe.set_user(h["requester"])
        with self.assertRaises(frappe.PermissionError):
            pilot.run_scts_uat_pilot_probe(h["biz"], apply=0)
        frappe.set_user("Administrator")
