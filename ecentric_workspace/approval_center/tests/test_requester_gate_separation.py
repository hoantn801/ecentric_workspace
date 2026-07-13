# Copyright (c) 2026, eCentric and contributors
"""Requester policy vs provider execution-gate separation (fix/scts-requester-policy-gate-
separation). Policy resolution (requester_signature_required) must NOT depend on the provider
write gates; the actual signing WRITE stays fail-closed behind the gates. Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_gate_separation
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import guard, requester
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

AR = "EC Approval Request"
SETTINGS = "EC Digital Signature Provider Settings"
BD, AT = "EC Payment Request", "PAYMENT_REQUEST"


def _scts_profile(requester_required=1):
    fx.ensure_process()
    fx.ensure_settings(allowed_users=None)
    fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": requester_required})


def _gates(integration=1, doc_creation=1, signing=1):
    name = frappe.db.get_value(SETTINGS, {"provider": "Mock", "environment": "UAT"}, "name")
    frappe.db.set_value(SETTINGS, name, {"integration_enabled": integration,
                                         "allow_document_creation": doc_creation,
                                         "allow_signing": signing})


class TestRequesterGateSeparation(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_policy_independent_of_signing_gate(self):
        # THE BUG: requester policy must resolve even with Allow Signing OFF.
        _scts_profile(); _gates(integration=1, doc_creation=0, signing=0)
        self.assertTrue(guard.requester_signature_required(BD, AT))
        # approver (gated) lookup remains gate-dependent -> inert while signing OFF (unchanged).
        self.assertIsNone(guard.get_active_profile(BD, AT))
        self.assertIsNotNone(guard.get_enabled_profile(BD, AT))

    def test_submit_defers_level1_with_signing_gate_off(self):
        _scts_profile(); _gates(integration=1, doc_creation=0, signing=0)
        h = fx.full_stack(fx.PFX + "gs1@example.com", fx.PFX + "gs1m@example.com")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "requester_signature_status"), "Pending")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 0)
        biz = frappe.db.get_value(AR, h["ar"], ["reference_doctype", "reference_name"], as_dict=True)
        self.assertEqual(frappe.db.count("ToDo", {"reference_type": biz.reference_doctype,
                                                  "reference_name": biz.reference_name,
                                                  "status": "Open"}), 0)

    def test_submit_and_sign_denied_when_doc_creation_off(self):
        _scts_profile(); _gates(integration=1, doc_creation=0, signing=1)
        h = fx.full_stack(fx.PFX + "gs2@example.com", fx.PFX + "gs2m@example.com")
        before = frappe.db.count("EC Digital Signature Request")
        frappe.set_user(h["requester"])
        with self.assertRaises(frappe.PermissionError):
            requester.requester_submit_and_sign(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("EC Digital Signature Request"), before)  # no DSR/write
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 0)

    def test_submit_and_sign_denied_when_signing_off(self):
        _scts_profile(); _gates(integration=1, doc_creation=1, signing=0)
        h = fx.full_stack(fx.PFX + "gs3@example.com", fx.PFX + "gs3m@example.com")
        frappe.set_user(h["requester"])
        with self.assertRaises(frappe.PermissionError):
            requester.requester_submit_and_sign(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "requester_signature_status"), "Pending")

    def test_disabled_profile_activates_level1(self):
        _scts_profile(); frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR", "enabled", 0)
        self.assertFalse(guard.requester_signature_required(BD, AT))
        h = fx.full_stack(fx.PFX + "gs4@example.com", fx.PFX + "gs4m@example.com")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 1)   # old behaviour
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "requester_signature_status"), "Not Required")

    def test_duplicate_enabled_profiles_fail_closed(self):
        _scts_profile()
        dup = "ZZESN_PAYR_DUP"
        if not frappe.db.exists("EC Digital Signature Profile", dup):
            frappe.get_doc({"doctype": "EC Digital Signature Profile", "profile_code": dup,
                            "title": "dup", "business_doctype": BD, "approval_type": AT,
                            "provider": "Mock", "environment": "UAT", "enabled": 1,
                            "approver_signature_policy": "All Approval Levels",
                            "provider_creation_trigger": "Before First Signing Level",
                            "doc_code_source": "name", "title_source": "request_title",
                            "amount_source": "payment_amount", "description_source": "reason"
                            }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            guard.get_enabled_profile(BD, AT)
        frappe.delete_doc("EC Digital Signature Profile", dup, ignore_permissions=True, force=True)

    def test_all_gates_on_readiness_can_proceed(self):
        _scts_profile(); _gates(1, 1, 1)
        for u in fx.full_stack(fx.PFX + "gs5@example.com", fx.PFX + "gs5m@example.com")["approvers"]:
            fx.ensure_mapping(u)
        h = fx.full_stack(fx.PFX + "gs6@example.com", fx.PFX + "gs6m@example.com")
        fx.ensure_mapping(h["requester"])
        frappe.set_user(h["requester"])
        rd = requester.requester_signing_readiness(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(rd["checks"].get("gates_enabled"))
