# Copyright (c) 2026, eCentric and contributors
"""UAT pilot readiness resolves the authoritative Approval Request by ITS OWN reference
fields (fix/scts-requester-readiness-resolution). Reproduces the deployed EC-PAYR/EC-APR case.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_pilot_readiness_resolution
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import guard, pilot
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

AR = "EC Approval Request"
SETTINGS = "EC Digital Signature Provider Settings"
BD, AT = "EC Payment Request", "PAYMENT_REQUEST"


def _scts_profile(requester=1):
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"provider": "SCTS", "environment": "UAT",
                         "approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": requester,
                         "workflow_definition_id": "WF", "document_type_id": "DT",
                         "company_id": "C", "department_id": "D", "document_template_id": "T"})


def _scts_settings(signing=0, doc_creation=0, allow=None):
    nm = frappe.db.get_value(SETTINGS, {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "base_url_allowlist": "scts.uat.local",
            "username": "erp-bot", "integration_enabled": 1,
            "allow_document_creation": doc_creation, "allow_signing": signing,
            "allow_production_signing": 0, "allow_callback": 0, "allow_bulk_signing": 0,
            "allowed_signing_users": allow or ""}
    if nm:
        d = frappe.get_doc(SETTINGS, nm); d.update(vals); d.save(ignore_permissions=True)
    else:
        frappe.get_doc(dict({"doctype": SETTINGS, "provider": "SCTS", "environment": "UAT"},
                            **vals)).insert(ignore_permissions=True)


class TestPilotReadinessResolution(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_deployed_case_ar_first_resolution(self):
        # exact deployed shape: AR carries the truth; PR back-link/approval_type may be blank.
        _scts_profile(requester=1); _scts_settings(signing=0, doc_creation=0)
        h = fx.full_stack(fx.PFX + "rr1r@x.com", fx.PFX + "rr1m@x.com")
        frappe.db.set_value(AR, h["ar"], {"requester_signature_status": "Pending",
                                          "current_level": 0, "approval_status": "Pending"})
        # simulate the deployed condition: PR back-link + approval_type blank
        frappe.db.set_value(BD, h["biz"], {"approval_request": None, "approval_type": None})
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertEqual(out["stage"], "Requester Pre-Approval")
        self.assertEqual(out["actor_type"], "Requester")
        self.assertTrue(out["checks"]["requester_stage_detected"]["ok"])
        for k in ("active_approver_in_uat_allowlist", "exact_active_profile_for_approval_type",
                  "active_approver_resolved", "level_resolved"):
            self.assertNotIn(k, out["blocking_items"])

    def test_missing_linked_ar_returns_diagnostics(self):
        _scts_profile(requester=1); _scts_settings()
        biz = fx.draft_payment_request(fx.user(fx.PFX + "rr2@x.com"))  # never submitted -> no AR
        out = pilot.uat_pilot_readiness(biz)
        self.assertIn(out["stage"], ("Unresolved", "No Active Stage"))
        self.assertIn("payment_request_resolved", out["checks"])
        self.assertIn("approval_request_resolved", out["checks"])
        self.assertFalse(out["checks"]["approval_request_resolved"]["ok"])

    def test_wrong_profile_approval_type_no_requester_stage(self):
        _scts_profile(requester=1); _scts_settings()
        h = fx.full_stack(fx.PFX + "rr3r@x.com", fx.PFX + "rr3m@x.com")
        frappe.db.set_value(AR, h["ar"], {"requester_signature_status": "Pending",
                                          "current_level": 0, "approval_status": "Pending",
                                          "approval_type": "OTHER_TYPE_NO_PROFILE"})
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertNotEqual(out["stage"], "Requester Pre-Approval")

    def test_duplicate_enabled_profiles_fail_closed(self):
        _scts_profile(requester=1); _scts_settings()
        dup = "ZZESN_PAYR_DUP2"
        if not frappe.db.exists("EC Digital Signature Profile", dup):
            frappe.get_doc({"doctype": "EC Digital Signature Profile", "profile_code": dup,
                            "title": "dup", "business_doctype": BD, "approval_type": AT,
                            "provider": "SCTS", "environment": "UAT", "enabled": 1,
                            "approver_signature_policy": "All Approval Levels",
                            "requester_signature_required": 1,
                            "provider_creation_trigger": "Before First Signing Level",
                            "doc_code_source": "name", "title_source": "request_title",
                            "amount_source": "payment_amount", "description_source": "reason"
                            }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            guard.get_enabled_profile(BD, AT)
        frappe.delete_doc("EC Digital Signature Profile", dup, ignore_permissions=True, force=True)

    def test_approval_stage_unchanged(self):
        _scts_profile(requester=0); _scts_settings(signing=1, doc_creation=1)
        h = fx.full_stack(fx.PFX + "rr4r@x.com", fx.PFX + "rr4m@x.com")
        out = pilot.uat_pilot_readiness(h["biz"])
        self.assertEqual(out["actor_type"], "Approval Level")
        self.assertIn("exact_active_profile_for_approval_type", out["checks"])
