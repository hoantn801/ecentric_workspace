# Copyright (c) 2026, eCentric and contributors
"""ERP-side signer-binding security matrix (esign.binding.assert_outbound_binding).

Proves the pre-write gate fails closed on every broken link of the invariant chain
    ERP active approver == verified mapping == outbound userId == live signature owner
and that NO provider write happens after any failed validation - including when the
caller is Administrator (there is no role bypass).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_binding_security
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import binding
from ecentric_workspace.approval_center.esign import service as esvc
from ecentric_workspace.approval_center.esign import tasks
from ecentric_workspace.approval_center.esign.providers.base import (
    NormalizedDocState, ProviderError, VerificationResult)
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

DSR = "EC Digital Signature Request"


class _StubAdapter(object):
    """Live-probe double: only validate_signature_owner is exercised by the binding."""

    def __init__(self, ok=True, reason="verified_owner"):
        self._ok = ok
        self._reason = reason
        self.owner_calls = 0

    def validate_signature_owner(self, mapped_user, signature_id):
        self.owner_calls += 1
        return VerificationResult(self._ok, self._reason)


class TestSctsBindingSecurity(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _queued(self, req="b_r@example.com", mgr="b_m@example.com"):
        h = fx.full_stack(fx.PFX + req, fx.PFX + mgr)
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        return h, res["signature_request"]

    # ---- baseline ----
    def test_happy_path_passes_and_probes_live_owner(self):
        h, dsr = self._queued("h1r", "h1m")
        stub = _StubAdapter(ok=True)
        self.assertTrue(binding.assert_outbound_binding(dsr, stub))
        self.assertEqual(stub.owner_calls, 1)

    # ---- ERP identity chain ----
    def test_wrong_erp_actor_blocked(self):
        h, dsr = self._queued("h2r", "h2m")
        row = frappe.db.get_value(DSR, dsr, "approver_row")
        frappe.db.set_value("EC Approval Request Approver", row, "approver", fx.CEO)
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    def test_wrong_runtime_level_blocked(self):
        h, dsr = self._queued("h3r", "h3m")
        frappe.db.set_value("EC Approval Request", h["ar"], "current_level", 2)
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    def test_mismatched_scts_userid_blocked(self):
        h, dsr = self._queued("h4r", "h4m")
        frappe.db.set_value(DSR, dsr, "effective_scts_user_id", "SCTS-INTRUDER")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    def test_outbound_signatureid_mismatch_blocked(self):
        h, dsr = self._queued("h5r", "h5m")
        frappe.db.set_value(DSR, dsr, "effective_signature_id", "SIG-FORGED")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    # ---- live provider ownership ----
    def test_foreign_signature_live_blocked_and_no_further(self):
        h, dsr = self._queued("h6r", "h6m")
        stub = _StubAdapter(ok=False, reason="signature_owner_mismatch")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, stub)
        self.assertEqual(stub.owner_calls, 1)

    def test_inactive_signature_live_blocked(self):
        h, dsr = self._queued("h7r", "h7m")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter(ok=False, reason="signature_inactive"))

    # ---- package integrity ----
    def test_package_hash_mismatch_blocked(self):
        h, dsr = self._queued("h8r", "h8m")
        frappe.db.set_value(DSR, dsr, "package_hash", "deadbeef")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    # ---- allowlist ----
    def test_non_allowlisted_user_blocked(self):
        h, dsr = self._queued("h9r", "h9m")
        name = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": "Mock", "environment": "UAT"}, "name")
        frappe.db.set_value("EC Digital Signature Provider Settings", name,
                            "allowed_signing_users", "")  # empty = nobody
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    # ---- provider environment ----
    def test_production_provider_blocked(self):
        with self.assertRaises(frappe.PermissionError):
            binding.assert_provider_uat({"environment": "Production"})
        # UAT passes the environment gate
        self.assertIsNone(binding.assert_provider_uat({"environment": "UAT"}))

    # ---- no role bypass ----
    def test_administrator_has_no_bypass(self):
        h, dsr = self._queued("h10r", "h10m")
        frappe.db.set_value(DSR, dsr, "effective_scts_user_id", "SCTS-INTRUDER")
        self.assertEqual(frappe.session.user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            binding.assert_outbound_binding(dsr, _StubAdapter())

    # ---- no SCTS write after failed validation (worker path) ----
    def test_no_provider_write_after_failed_validation(self):
        from ecentric_workspace.approval_center.esign.providers.mock import MockAdapter
        h, dsr = self._queued("h11r", "h11m")
        frappe.db.set_value(DSR, dsr, "effective_signature_id", "SIG-FORGED")  # break chain
        writes = {"create": 0, "bulk": 0}
        real_create = MockAdapter.create_document
        real_bulk = MockAdapter.approve_and_sign

        def spy_create(self, *a, **k):
            writes["create"] += 1
            return real_create(self, *a, **k)

        def spy_bulk(self, *a, **k):
            writes["bulk"] += 1
            return real_bulk(self, *a, **k)

        with patch.object(MockAdapter, "create_document", spy_create), \
                patch.object(MockAdapter, "approve_and_sign", spy_bulk):
            tasks.process_signing_request(dsr)
        self.assertEqual(writes, {"create": 0, "bulk": 0})  # gate ran before any write
        st = frappe.db.get_value(DSR, dsr, ["status", "error_code"], as_dict=True)
        self.assertEqual(st.status, "Permanent Failure")  # security refusal, not retryable
        self.assertEqual(st.error_code, "binding_refused")

    # ---- worker-level failure classification (B4) ----
    def _run_worker_with_owner(self, dsr, owner_result=None, transient=False):
        from ecentric_workspace.approval_center.esign import tasks as _t
        calls = {"bulk": 0}

        class _OwnStub(object):
            def validate_signature_owner(self, u, s):
                if transient:
                    raise ProviderError("scts_server_error_503", "provider outage",
                                        retryable=True)
                return owner_result

            def approve_and_sign(self, *a, **k):
                calls["bulk"] += 1
                return {"bulk_job_transaction_id": "x"}

            def create_document(self, ctx):
                calls["bulk"] += 1  # any provider write counts
                return {"document_id": "d", "files": []}

            def poll_status(self, d):
                return NormalizedDocState(d, "in_progress")

        with patch.object(_t, "get_adapter", lambda s: _OwnStub()):
            _t.process_signing_request(dsr)
        return calls["bulk"]

    def test_worker_ownership_mismatch_permanent_no_bulk(self):
        h, dsr = self._queued("h12r", "h12m")
        bulk = self._run_worker_with_owner(
            dsr, owner_result=VerificationResult(False, "signature_owner_mismatch"))
        self.assertEqual(bulk, 0)  # no provider write after a failed security validation
        st = frappe.db.get_value(DSR, dsr, ["status", "error_code"], as_dict=True)
        self.assertEqual(st.status, "Permanent Failure")  # non-retryable security failure
        self.assertEqual(st.error_code, "binding_refused")

    def test_worker_transient_getsignatures_retryable_no_bulk(self):
        h, dsr = self._queued("h13r", "h13m")
        bulk = self._run_worker_with_owner(dsr, transient=True)
        self.assertEqual(bulk, 0)  # availability failure still performs no write
        st = frappe.db.get_value(DSR, dsr, ["status", "retryable"], as_dict=True)
        self.assertEqual(st.status, "Retryable Failure")  # transient stays retryable
        self.assertEqual(st.retryable, 1)
