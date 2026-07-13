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
    # the PR's approval_type is read-only and unset by the draft flow; populate it so the
    # exact active-profile resolver (guard.get_active_profile) has a key to match.
    frappe.db.set_value("EC Payment Request", h["biz"], "approval_type", "PAYMENT_REQUEST")
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


DSR = "EC Digital Signature Request"
DSF = "EC Digital Signature File"


def _active_dsr(pkg_name, key, user_id="U", status="Queued"):
    return frappe.get_doc({
        "doctype": DSR, "provider": "SCTS", "environment": "UAT", "package": pkg_name,
        "approval_request": "AR-DUMMY", "request_level": "LVL-DUMMY",
        "approver_row": "ROW-DUMMY", "action": "Sign", "requested_by": "Administrator",
        "approver": "Administrator", "idempotency_key": key,
        "effective_scts_user_id": user_id, "status": status,
    }).insert(ignore_permissions=True, ignore_links=True).name


class TestUatPilotReadinessBlocker3(FrappeTestCase):
    """PR#147 blocker 3: exact-profile-only resolution, blocking duplicate DSR, and
    fail-closed structured file readiness."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_exact_profile_and_one_dsr_passes(self):
        h = _ready_stack("b31r", "b31m")
        _active_dsr(h["pkg"], "idem-b31-1")  # exactly one active DSR
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(out["checks"]["exact_active_profile_for_approval_type"]["ok"])
        self.assertTrue(out["checks"]["no_active_duplicate_dsr"]["ok"])
        self.assertTrue(out["ready"], "blocking: %s" % out["blocking_items"])

    def test_duplicate_active_dsr_blocks(self):
        h = _ready_stack("b32r", "b32m")
        _active_dsr(h["pkg"], "idem-b32-1", status="Queued")
        _active_dsr(h["pkg"], "idem-b32-2", status="Provider Accepted")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("no_active_duplicate_dsr", out["blocking_items"])  # now BLOCKING
        self.assertFalse(out["ready"])

    def test_missing_exact_profile_blocks(self):
        h = _ready_stack("b33r", "b33m")
        # no profile exists for this approval_type -> must block, must NOT fall back
        frappe.db.set_value("EC Payment Request", h["biz"], "approval_type", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("exact_active_profile_for_approval_type", out["blocking_items"])
        self.assertFalse(out["ready"])

    def test_unrelated_enabled_profile_not_used(self):
        h = _ready_stack("b34r", "b34m")
        # an unrelated enabled SCTS profile exists for a DIFFERENT approval_type ...
        if not frappe.db.exists("EC Approval Type", "OTHER_TYPE"):
            frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "OTHER_TYPE",
                            "title": "Other"}).insert(ignore_permissions=True)
        if not frappe.db.exists("EC Digital Signature Profile", "ZZESN_OTHER"):
            frappe.get_doc({
                "doctype": "EC Digital Signature Profile", "profile_code": "ZZESN_OTHER",
                "title": "ZZESN Other", "business_doctype": "EC Payment Request",
                "approval_type": "OTHER_TYPE", "provider": "SCTS", "environment": "UAT",
                "enabled": 1, "provider_creation_trigger": "Before First Signing Level",
                "doc_code_source": "name", "title_source": "request_title",
                "amount_source": "payment_amount", "description_source": "reason",
                "levels": [{"level_no": 1, "requires_signature": 1,
                            "mandatory_placements_per_file": 1}],
                "transitions": [{"action": "Reject", "transition_id": -16}],
            }).insert(ignore_permissions=True)
        # ... but the PR's own approval_type has no matching profile
        frappe.db.set_value("EC Payment Request", h["biz"], "approval_type", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])
        frappe.set_user("Administrator")
        # must still block: the unrelated enabled profile must NOT be used as a fallback
        self.assertIn("exact_active_profile_for_approval_type", out["blocking_items"])
        self.assertFalse(out["ready"])

    def test_missing_file_link_blocks_without_traceback(self):
        h = _ready_stack("b35r", "b35m")
        # clear the File link on a signable row -> structured blocking item, no exception
        row = frappe.get_all(DSF, filters={"package": h["pkg"], "requires_signature": 1},
                             pluck="name")[0]
        frappe.db.set_value(DSF, row, "file", "")
        frappe.set_user(h["mgr"])
        out = pilot.uat_pilot_readiness(h["biz"])  # must not raise
        frappe.set_user("Administrator")
        self.assertIn("all_signable_files_have_file_link", out["blocking_items"])
        self.assertFalse(out["ready"])
