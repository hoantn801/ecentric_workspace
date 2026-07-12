# Copyright (c) 2026, eCentric and contributors
"""S2B-A remote-review hardening (pure, mocked transport): SignerSignatureId field,
fail-closed signature status, one-attempt ambiguous bulk-process, and transient-vs-
security classification of the ownership probe.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_hardening
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts import SctsAdapter
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient
from ecentric_workspace.approval_center.tests import scts_fixtures as sx


def _client(script, retry_limit=3):
    t = sx.FakeTransport(script)
    return SctsClient("https://scts.uat.local", timeout=5, retry_limit=retry_limit,
                      transport=t, sleeper=lambda *_: None), t


def _adapter(script):
    t = sx.FakeTransport(script)
    ad = sx.make_adapter(t)
    ad._password = lambda f: {"password": "pw", "token_cache": "tok"}.get(f)
    ad._store_token = lambda *a, **k: None
    ad._cached_token = lambda: "tok"
    return ad, t


class TestSctsHardening(FrappeTestCase):
    # -- B1: bulk-process field contract --
    def test_bulk_sends_SignerSignatureId_not_signatureId(self):
        c, t = _client({"bulk_process": sx.bulk_ok("X")})
        c.bulk_process(["D1", "D2"], "U1", "SIG-U1", 5, "tok")
        b = t.last_body("bulk_process")
        self.assertEqual(b["SignerSignatureId"], "SIG-U1")
        self.assertNotIn("signatureId", b)
        self.assertEqual((b["instanceIds"], b["userId"], b["transitionType"]),
                         (["D1", "D2"], "U1", 5))

    # -- B3: one-attempt ambiguous bulk-process --
    def test_bulk_network_single_attempt_ambiguous(self):
        c, t = _client({"bulk_process": ConnectionError("lost")})
        with self.assertRaises(ProviderError) as e:
            c.bulk_process(["D"], "U", "SIG", None, "tok")
        self.assertEqual(e.exception.code, "scts_bulk_outcome_unknown")
        self.assertTrue(e.exception.ambiguous)
        self.assertFalse(e.exception.retryable)
        self.assertEqual(t.count("bulk_process"), 1)

    def test_bulk_5xx_single_attempt_ambiguous(self):
        c, t = _client({"bulk_process": sx.FakeResponse(503, {})})
        with self.assertRaises(ProviderError) as e:
            c.bulk_process(["D"], "U", "SIG", None, "tok")
        self.assertTrue(e.exception.ambiguous)
        self.assertEqual(t.count("bulk_process"), 1)

    def test_bulk_4xx_hard_rejection_not_ambiguous(self):
        c, t = _client({"bulk_process": sx.FakeResponse(422, {})})
        with self.assertRaises(ProviderError) as e:
            c.bulk_process(["D"], "U", "SIG", None, "tok")
        self.assertFalse(e.exception.ambiguous)
        self.assertFalse(e.exception.retryable)
        self.assertTrue(e.exception.code.startswith("scts_bulk_rejected"))
        self.assertEqual(t.count("bulk_process"), 1)

    def test_read_calls_still_retry(self):
        c, t = _client({"get_document": [sx.FakeResponse(500, {}),
                                         sx.document("D", "U", "SIG-U")]}, retry_limit=2)
        self.assertEqual(c.get_document("D", "tok")["id"], "D")
        self.assertEqual(t.count("get_document"), 2)

    # -- B2: fail-closed signature status --
    def test_resolve_active_fail_closed_matrix(self):
        ra = SctsAdapter._resolve_active
        self.assertTrue(ra({"isActive": True}))
        self.assertTrue(ra({"active": True}))
        self.assertTrue(ra({"status": "active"}))
        self.assertTrue(ra({"status": "valid"}))
        self.assertTrue(ra({"status": "usable"}))
        self.assertFalse(ra({"isActive": False}))
        self.assertFalse(ra({"status": "inactive"}))
        self.assertFalse(ra({"status": "revoked"}))
        self.assertFalse(ra({"status": "expired"}))
        self.assertFalse(ra({}))               # missing all evidence -> inactive
        self.assertFalse(ra({"status": ""}))   # empty status -> inactive
        self.assertFalse(ra({"isActive": "false"}))

    # -- B4: ownership probe classification --
    def test_transient_getsignatures_propagates_retryable(self):
        ad, t = _adapter({"get_signatures": [sx.FakeResponse(500, {}), sx.FakeResponse(500, {}),
                                             sx.FakeResponse(500, {})]})
        with self.assertRaises(ProviderError) as e:
            ad.validate_signature_owner("U1", "SIG-U1")
        self.assertTrue(e.exception.retryable)
        self.assertFalse(e.exception.ambiguous)

    def test_ownership_mismatch_returns_false_not_raise(self):
        ad, t = _adapter({"get_signatures": sx.signatures_for("U1", "SIG-U1")})
        vr = ad.validate_signature_owner("U1", "SIG-OTHER")
        self.assertFalse(vr.ok)

    def test_adapter_bulk_propagates_ambiguous(self):
        ad, t = _adapter({"bulk_process": ConnectionError("lost")})
        with self.assertRaises(ProviderError) as e:
            ad.approve_and_sign(["D"], "U1", "SIG-U1")
        self.assertTrue(e.exception.ambiguous)
        self.assertEqual(e.exception.code, "scts_bulk_outcome_unknown")
