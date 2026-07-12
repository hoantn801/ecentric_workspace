# Copyright (c) 2026, eCentric and contributors
"""Idempotency + concurrency: duplicate approve_and_sign returns the same DSR (one
provider submission), unique key backstop, retry gating.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_idempotency
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import service as esvc
from ecentric_workspace.approval_center.esign.providers.mock import MockAdapter
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestEsignIdempotency(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_duplicate_call_returns_same_dsr_single_submission(self):
        h = fx.full_stack(fx.PFX + "i1r@example.com", fx.PFX + "i1m@example.com")
        frappe.set_user(h["mgr"])
        r1 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        r2 = esvc.approve_and_sign("EC Payment Request", h["biz"])  # double-click
        frappe.set_user("Administrator")
        self.assertEqual(r1["signature_request"], r2["signature_request"])
        self.assertTrue(r2["duplicate"])
        n = frappe.db.count("EC Digital Signature Request",
                            {"approval_request": h["ar"], "action": "Sign"})
        self.assertEqual(n, 1)

    def test_duplicate_after_worker_still_returns_done_row(self):
        h = fx.full_stack(fx.PFX + "i2r@example.com", fx.PFX + "i2m@example.com")
        frappe.set_user(h["mgr"])
        r1 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        fx.run_worker_for_latest(h["ar"])
        frappe.set_user(h["mgr"])
        # level may already be completed -> pending-approver preflight throws OR
        # duplicate short-circuit returns the completed row; both are correct,
        # a SECOND provider submission is what must never happen.
        try:
            r2 = esvc.approve_and_sign("EC Payment Request", h["biz"])
            self.assertEqual(r1["signature_request"], r2["signature_request"])
        except Exception:
            pass
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("EC Digital Signature Request",
                                         {"approval_request": h["ar"], "action": "Sign"}), 1)

    def test_unique_key_is_db_enforced(self):
        h = fx.full_stack(fx.PFX + "i3r@example.com", fx.PFX + "i3m@example.com")
        frappe.set_user(h["mgr"])
        r1 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        key = frappe.db.get_value("EC Digital Signature Request", r1["signature_request"],
                                  "idempotency_key")
        dup = frappe.get_doc({
            "doctype": "EC Digital Signature Request", "provider": "Mock",
            "environment": "UAT", "package": h["pkg"], "approval_request": h["ar"],
            "request_level": frappe.db.get_value("EC Digital Signature Request",
                                                 r1["signature_request"], "request_level"),
            "approver_row": frappe.db.get_value("EC Digital Signature Request",
                                                r1["signature_request"], "approver_row"),
            "requested_by": h["mgr"], "approver": h["mgr"],
            "idempotency_key": key, "status": "Draft"})
        with self.assertRaises(Exception):  # UniqueValidationError / IntegrityError
            dup.insert(ignore_permissions=True)

    def test_retry_requires_sm_and_manual_review_state(self):
        h = fx.full_stack(fx.PFX + "i4r@example.com", fx.PFX + "i4m@example.com",
                          site="fail:create")
        frappe.set_user(h["mgr"])
        r1 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        fx.run_worker_for_latest(h["ar"])  # -> Retryable Failure
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            esvc.retry_signature_request(r1["signature_request"])  # not SM
        frappe.set_user("Administrator")
        MockAdapter.reset()
        fx.ensure_settings(allowed_users=h["approvers"], site="")  # heal the mock
        out = esvc.retry_signature_request(r1["signature_request"])
        self.assertTrue(out["queued"])
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request",
                                             r1["signature_request"], "request_attempt"), 2)
