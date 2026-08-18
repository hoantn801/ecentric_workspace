# Copyright (c) 2026, eCentric and contributors
"""esign.flow.drift + its one wiring point (payment_request.activation.publish_*).
Confirms: (1) drift.check() is System-Manager-only and read-only; (2) drift.blockers()
is [] with no enabled Profile and with a Profile that matches EXPECTED_PROFILE_POLICY;
(3) it reports a mismatch when the Profile diverges; (4) publish_payment_request_after_uat
is blocked by that mismatch and never writes when blocked - this is the only live path
this Phase-1/2 work touches, so it is the one path that needs a real integration test.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_flow_drift
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.platform.esign.flow import drift
from ecentric_workspace.approval_center.payment_request import activation
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

PROFILE = "ZZESN_PAYR"


class TestEsignFlowDrift(FrappeTestCase):
    def setUp(self):
        fx.ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    # ---------------- drift.check() access control ---------------- #
    def test_check_requires_system_manager(self):
        u = fx.user("zzesn_nonsm@example.com", roles=("Employee",))
        frappe.set_user(u)
        with self.assertRaises(frappe.PermissionError):
            drift.check()

    def test_check_is_read_only_regardless_of_result(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 0)  # mismatch vs EXPECTED (1)
        before = frappe.db.get_value("EC Digital Signature Profile", PROFILE,
                                     "requester_signature_required")
        drift.check()
        after = frappe.db.get_value("EC Digital Signature Profile", PROFILE,
                                    "requester_signature_required")
        self.assertEqual(before, after)

    # ---------------- drift.blockers() ---------------- #
    def test_no_enabled_profile_is_not_a_blocker(self):
        # esign simply not in play for this pair - absence must not read as drift.
        self.assertEqual(drift.blockers(), [])

    def test_matching_profile_has_no_blockers(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()  # approver_signature_policy defaults to 'All Approval Levels'
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 1)
        self.assertEqual(drift.blockers(), [])

    def test_mismatched_requester_signature_required_is_a_blocker(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 0)  # EXPECTED is 1
        out = drift.blockers()
        self.assertEqual(len(out), 1)
        self.assertIn("requester_signature_required", out[0])
        self.assertIn(PROFILE, out[0])

    def test_mismatched_approver_signature_policy_is_a_blocker(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 1)
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "approver_signature_policy", "Final Approval Level Only")
        out = drift.blockers()
        self.assertEqual(len(out), 1)
        self.assertIn("approver_signature_policy", out[0])

    def test_two_enabled_profiles_is_reported_not_silently_resolved(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        dupe = frappe.copy_doc(frappe.get_doc("EC Digital Signature Profile", PROFILE))
        dupe.profile_code = "ZZESN_PAYR_DUPE"
        dupe.name = None
        dupe.insert(ignore_permissions=True)
        try:
            out = drift.blockers()
            self.assertEqual(len(out), 1)
            self.assertIn("ambiguous_or_lookup_failed", out[0])
        finally:
            frappe.delete_doc("EC Digital Signature Profile", "ZZESN_PAYR_DUPE",
                              ignore_permissions=True, force=True)

    # ---------------- wiring: publish_payment_request_after_uat ---------------- #
    def test_publish_blocked_by_esign_drift_even_when_process_ready(self):
        # setUp()'s fx.ensure_process() already leaves PAYMENT_REQUEST-V1 Active.
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 0)  # induces drift

        before_card = frappe.db.get_value("EC Approval Type", activation.TYPE, "card_status")
        report = activation.publish_payment_request_after_uat(apply=1)

        self.assertFalse(report["ready"])
        self.assertTrue(any("esign flow drift" in b for b in report["blockers"]))
        self.assertEqual(report["result"].split(" ", 1)[0], "BLOCKED")
        # never wrote card_status when blocked
        self.assertEqual(frappe.db.get_value("EC Approval Type", activation.TYPE, "card_status"),
                         before_card)

    def test_publish_not_blocked_by_esign_when_profile_matches(self):
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 1)

        report = activation.publish_payment_request_after_uat(apply=0)  # dry-run: no writes either way
        self.assertFalse(any("esign flow drift" in b for b in report["blockers"]))
