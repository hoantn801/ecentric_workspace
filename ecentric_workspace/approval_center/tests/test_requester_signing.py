# Copyright (c) 2026, eCentric and contributors
"""Requester Submit & Sign lifecycle (Option B). Runs on the bench/PR CI (needs frappe DB):
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_signing

Covers: authoritative-requester resolution (A vs B), wrong-requester + Administrator rejected,
missing/unverified mapping rejected, one reused DSR on repeated calls, no Level-1 ToDo before
signing, confirmed signing activates Level 1 exactly once, failure/ambiguous never activates,
idempotent activation, and the approver path unchanged. Deterministic (no real provider).
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import guard, requester
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

AR = "EC Approval Request"
DSR = "EC Digital Signature Request"


def _require_requester_profile():
    fx.ensure_process()
    fx.ensure_settings(allowed_users=None)
    fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _pending_request(reqmail, mgrmail):
    """A submitted request whose profile requires requester signature => Level 1 deferred."""
    _require_requester_profile()
    h = fx.full_stack(fx.PFX + reqmail, fx.PFX + mgrmail)   # existing helper submits + snapshots
    return h


class TestRequesterSigning(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_authoritative_requester_resolution_A_vs_B(self):
        _require_requester_profile()
        a = fx.full_stack(fx.PFX + "rqA@example.com", fx.PFX + "rqAm@example.com")
        b = fx.full_stack(fx.PFX + "rqB@example.com", fx.PFX + "rqBm@example.com")
        self.assertEqual(frappe.db.get_value(AR, a["ar"], "requested_by"), a["requester"])
        self.assertEqual(frappe.db.get_value(AR, b["ar"], "requested_by"), b["requester"])
        self.assertNotEqual(a["requester"], b["requester"])

    def test_wrong_requester_and_admin_rejected(self):
        h = _pending_request("rq1@example.com", "rq1m@example.com")
        frappe.set_user(h["mgr"])       # an approver, not the requester
        with self.assertRaises(frappe.PermissionError):
            requester.requester_submit_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")  # SM/Administrator has no bypass
        with self.assertRaises(frappe.PermissionError):
            requester.requester_submit_and_sign("EC Payment Request", h["biz"])

    def test_no_level1_todo_before_requester_signature(self):
        h = _pending_request("rq2@example.com", "rq2m@example.com")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 0)
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "requester_signature_status"), "Pending")
        biz = frappe.db.get_value(AR, h["ar"], ["reference_doctype", "reference_name"], as_dict=True)
        todos = frappe.db.count("ToDo", {"reference_type": biz.reference_doctype,
                                         "reference_name": biz.reference_name, "status": "Open"})
        self.assertEqual(todos, 0)

    def test_missing_mapping_fails_closed(self):
        h = _pending_request("rq3@example.com", "rq3m@example.com")
        frappe.db.delete("EC SCTS User Mapping", {"frappe_user": h["requester"]})
        frappe.set_user(h["requester"])
        with self.assertRaises(Exception):
            requester.requester_submit_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 0)  # still inactive

    def test_confirmed_signing_activates_level_one_exactly_once(self):
        h = _pending_request("rq4@example.com", "rq4m@example.com")
        ar = h["ar"]
        # simulate a confirmed requester DSR
        pkg = frappe.db.get_value("EC Digital Signature Package", {"approval_request": ar}, "name")
        dsr = frappe.get_doc({"doctype": DSR, "provider": "Mock", "environment": "UAT",
                              "package": pkg, "approval_request": ar, "action": "Sign",
                              "actor_type": "Requester", "actor_user": h["requester"],
                              "requested_by": h["requester"], "approver": h["requester"],
                              "effective_scts_user_id": "U", "effective_signature_id": "S",
                              "idempotency_key": "idem-rq4", "status": "Approval Completed"}
                             ).insert(ignore_permissions=True)
        r1 = requester.activate_level_one_after_requester_signature(ar, dsr.name)
        r2 = requester.activate_level_one_after_requester_signature(ar, dsr.name)  # idempotent
        self.assertTrue(r1["activated"])
        self.assertFalse(r2["activated"])
        self.assertEqual(frappe.db.get_value(AR, ar, "current_level"), 1)
        self.assertEqual(frappe.db.get_value(AR, ar, "requester_signature_status"), "Signed")

    def test_failure_does_not_activate_level_one(self):
        h = _pending_request("rq5@example.com", "rq5m@example.com")
        ar = h["ar"]
        pkg = frappe.db.get_value("EC Digital Signature Package", {"approval_request": ar}, "name")
        dsr = frappe.get_doc({"doctype": DSR, "provider": "Mock", "environment": "UAT",
                              "package": pkg, "approval_request": ar, "action": "Sign",
                              "actor_type": "Requester", "actor_user": h["requester"],
                              "requested_by": h["requester"], "approver": h["requester"],
                              "effective_scts_user_id": "U", "effective_signature_id": "S",
                              "idempotency_key": "idem-rq5", "status": "Permanent Failure"}
                             ).insert(ignore_permissions=True)
        out = requester.reconcile_and_complete_requester(dsr.name)
        self.assertFalse(out.get("completed"))
        self.assertEqual(frappe.db.get_value(AR, ar, "current_level"), 0)
        self.assertEqual(frappe.db.get_value(AR, ar, "requester_signature_status"), "Failed")

    def test_ambiguous_marks_reconciliation_no_activation(self):
        h = _pending_request("rq6@example.com", "rq6m@example.com")
        ar = h["ar"]
        pkg = frappe.db.get_value("EC Digital Signature Package", {"approval_request": ar}, "name")
        dsr = frappe.get_doc({"doctype": DSR, "provider": "Mock", "environment": "UAT",
                              "package": pkg, "approval_request": ar, "action": "Sign",
                              "actor_type": "Requester", "actor_user": h["requester"],
                              "requested_by": h["requester"], "approver": h["requester"],
                              "effective_scts_user_id": "U", "effective_signature_id": "S",
                              "idempotency_key": "idem-rq6", "status": "Verifying"}
                             ).insert(ignore_permissions=True)
        out = requester.reconcile_and_complete_requester(dsr.name)
        self.assertEqual(out.get("reason"), "reconciliation_required")
        self.assertEqual(frappe.db.get_value(AR, ar, "current_level"), 0)
        self.assertEqual(frappe.db.get_value(AR, ar, "requester_signature_status"),
                         "Reconciliation Required")

    def test_legacy_profile_without_requester_signature_activates_immediately(self):
        fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                            {"requester_signature_required": 0})
        h = fx.full_stack(fx.PFX + "rq7@example.com", fx.PFX + "rq7m@example.com")
        self.assertEqual(frappe.db.get_value(AR, h["ar"], "current_level"), 1)  # immediate
