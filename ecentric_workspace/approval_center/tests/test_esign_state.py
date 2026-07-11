# Copyright (c) 2026, eCentric and contributors
"""PURE tests (no frappe, no DB): state machines, sanitizer, mock-adapter verification.
Runnable anywhere: python -m unittest ecentric_workspace.approval_center.tests.test_esign_state
"""
import unittest

from ecentric_workspace.approval_center.esign import state as sm
from ecentric_workspace.approval_center.esign.sanitize import REDACTED, safe_error, sanitize
from ecentric_workspace.approval_center.esign.providers.base import (
    NormalizedDocState, SignatureProviderAdapter,
)
from ecentric_workspace.approval_center.esign.providers.mock import MockAdapter


class TestStateMachine(unittest.TestCase):
    def test_every_declared_transition_is_between_known_states(self):
        for kind, states, table in ((sm.PACKAGE, sm.PACKAGE_STATES, sm.PACKAGE_TRANSITIONS),
                                    (sm.DSR, sm.DSR_STATES, sm.DSR_TRANSITIONS)):
            self.assertEqual(set(table.keys()), set(states), kind)
            for src, targets in table.items():
                for t in targets:
                    self.assertIn(t, states, "%s: %s -> %s" % (kind, src, t))

    def test_legal_happy_path_dsr(self):
        chain = ["Draft", "Prepared", "Queued", "Provider Accepted", "Verifying",
                 "Signed", "Approval Completed"]
        for a, b in zip(chain, chain[1:]):
            self.assertTrue(sm.assert_transition(sm.DSR, a, b))

    def test_poll_first_shortcut_queued_to_signed(self):
        self.assertTrue(sm.assert_transition(sm.DSR, "Queued", "Signed"))

    def test_three_concepts_never_collapse(self):
        # accepted != signed != completed: no direct edges skipping verification
        with self.assertRaises(sm.InvalidTransition):
            sm.assert_transition(sm.DSR, "Provider Accepted", "Approval Completed")
        with self.assertRaises(sm.InvalidTransition):
            sm.assert_transition(sm.DSR, "Queued", "Approval Completed")

    def test_terminals_have_no_exits(self):
        for s in ("Approval Completed", "Permanent Failure", "Rejected", "Superseded"):
            self.assertEqual(sm.DSR_TRANSITIONS[s], ())
        for s in ("Superseded", "Cancelled", "Completed"):
            self.assertEqual(sm.PACKAGE_TRANSITIONS[s], ())

    def test_illegal_and_unknown(self):
        with self.assertRaises(sm.InvalidTransition):
            sm.assert_transition(sm.DSR, "Signed", "Queued")
        with self.assertRaises(sm.InvalidTransition):
            sm.assert_transition(sm.DSR, "NotAState", "Queued")
        with self.assertRaises(sm.InvalidTransition):
            sm.assert_transition(sm.PACKAGE, "Draft", "Active")


class TestSanitize(unittest.TestCase):
    def test_sensitive_keys_redacted_recursively(self):
        out = sanitize({"password": "x", "nested": {"Authorization": "Bearer abc",
                                                    "PdfBase64": "AAAA", "ok": 1},
                        "items": [{"api_secret": "s"}]})
        self.assertEqual(out["password"], REDACTED)
        self.assertEqual(out["nested"]["Authorization"], REDACTED)
        self.assertEqual(out["nested"]["PdfBase64"], REDACTED)
        self.assertEqual(out["nested"]["ok"], 1)
        self.assertEqual(out["items"][0]["api_secret"], REDACTED)

    def test_bytes_and_long_strings_never_persist_raw(self):
        out = sanitize({"blob": b"\x00" * 100000, "long": "A" * 5000})
        self.assertEqual(out["blob"], "***bytes:100000***")
        self.assertTrue(out["long"].endswith("(truncated)"))

    def test_safe_error_withholds_sensitive_messages(self):
        e = ValueError("Bearer abc123 leaked")
        self.assertIn("withheld", safe_error(e))


class TestMockVerification(unittest.TestCase):
    def setUp(self):
        MockAdapter.reset()
        self.adapter = MockAdapter({"provider": "Mock", "site": ""})

    def _create(self):
        return self.adapter.create_document(
            {"files": [{"order": 0, "name": "a.pdf"}, {"order": 1, "name": "b.pdf"}]})

    def test_accept_is_not_success_then_verify(self):
        doc = self._create()
        res = self.adapter.approve_and_sign([doc["document_id"]], "U1", "SIG-U1")
        self.assertIn("bulk_job_transaction_id", res)
        state = self.adapter.poll_status(doc["document_id"])
        vr = SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": doc["document_id"], "user_id": "U1",
                    "signature_id": "SIG-U1", "file_count": 2})
        self.assertTrue(vr.ok)

    def test_wrong_signer_detected(self):
        self.adapter = MockAdapter({"provider": "Mock", "site": "wrong:signer"})
        doc = self._create()
        self.adapter.approve_and_sign([doc["document_id"]], "U1", "SIG-U1")
        state = self.adapter.poll_status(doc["document_id"])
        vr = SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": doc["document_id"], "user_id": "U1"})
        self.assertFalse(vr.ok)
        self.assertEqual(vr.reason, "expected_signer_absent")

    def test_never_sign_stays_unverified(self):
        self.adapter = MockAdapter({"provider": "Mock", "site": "never:sign"})
        doc = self._create()
        self.adapter.approve_and_sign([doc["document_id"]], "U1", "SIG-U1")
        state = self.adapter.poll_status(doc["document_id"])
        vr = SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": doc["document_id"], "user_id": "U1"})
        self.assertFalse(vr.ok)
        self.assertTrue(vr.reason.startswith("signer_not_signed"))

    def test_document_and_file_count_mismatch(self):
        doc = self._create()
        self.adapter.approve_and_sign([doc["document_id"]], "U1", "SIG-U1")
        state = self.adapter.poll_status(doc["document_id"])
        self.assertFalse(SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": "OTHER", "user_id": "U1"}).ok)
        self.assertFalse(SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": doc["document_id"], "user_id": "U1",
                    "file_count": 5}).ok)

    def test_partial_success_invalid_item_does_not_block(self):
        doc = self._create()
        self.adapter.approve_and_sign(["NO-SUCH-DOC", doc["document_id"]], "U1", "SIG-U1")
        state = self.adapter.poll_status(doc["document_id"])
        self.assertTrue(SignatureProviderAdapter.verify_signed_result(
            state, {"document_id": doc["document_id"], "user_id": "U1"}).ok)


if __name__ == "__main__":
    unittest.main()
