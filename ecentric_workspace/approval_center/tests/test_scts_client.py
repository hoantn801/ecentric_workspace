# Copyright (c) 2026, eCentric and contributors
"""SCTS client + adapter: deterministic HTTP behavior with a fake transport (no network).
Covers login success/failure, safe single re-login on 401, configurable timeout, bounded
retry for network/5xx, NO retry for validation/auth, malformed responses, GetSignatures
normalization, signature-ownership, bulk-process submit + txn extraction, and Document
status normalization (signed/pending/rejected + field-name variants).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_client
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient
from ecentric_workspace.approval_center.tests import scts_fixtures as sx


def _client(script, retry_limit=2):
    t = sx.FakeTransport(script)
    return SctsClient("https://scts.uat.local", timeout=5, retry_limit=retry_limit,
                      transport=t, sleeper=lambda *_: None), t


class TestSctsClient(FrappeTestCase):
    def test_login_success_returns_payload(self):
        c, t = _client({"login": sx.login_ok("tok", 60)})
        out = c.login("u", "p")
        self.assertEqual(out["token"], "tok")
        self.assertEqual(t.count("login"), 1)

    def test_login_failure_is_non_retryable_auth_error(self):
        c, t = _client({"login": sx.login_bad()})
        with self.assertRaises(ProviderError) as e:
            c.login("u", "p")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(e.exception.code, "scts_auth_failed")
        self.assertEqual(t.count("login"), 1)  # 4xx: never retried

    def test_network_error_retries_then_raises_retryable(self):
        c, t = _client({"get_document": ConnectionError("boom")}, retry_limit=2)
        with self.assertRaises(ProviderError) as e:
            c.get_document("D1", "tok")
        self.assertTrue(e.exception.retryable)
        self.assertEqual(t.count("get_document"), 3)  # initial + 2 retries

    def test_5xx_retries_then_succeeds(self):
        c, t = _client({"get_document": [sx.FakeResponse(503, {}),
                                         sx.document("D1", "U1", "SIG-U1")]}, retry_limit=2)
        raw = c.get_document("D1", "tok")
        self.assertEqual(raw["id"], "D1")
        self.assertEqual(t.count("get_document"), 2)

    def test_5xx_exhausted_raises_retryable(self):
        c, t = _client({"get_document": [sx.FakeResponse(500, {}), sx.FakeResponse(500, {}),
                                         sx.FakeResponse(500, {})]}, retry_limit=2)
        with self.assertRaises(ProviderError) as e:
            c.get_document("D1", "tok")
        self.assertTrue(e.exception.retryable)
        self.assertEqual(t.count("get_document"), 3)

    def test_validation_4xx_not_retried(self):
        c, t = _client({"bulk_process": sx.FakeResponse(422, {"error": "bad"})}, retry_limit=3)
        with self.assertRaises(ProviderError) as e:
            c.bulk_process(["D1"], "U1", "SIG-U1", None, "tok")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(t.count("bulk_process"), 1)

    def test_auth_403_on_call_is_non_retryable(self):
        c, t = _client({"get_signatures": sx.FakeResponse(403, {})}, retry_limit=2)
        with self.assertRaises(ProviderError) as e:
            c.get_signatures("U1", "tok")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(t.count("get_signatures"), 1)

    def test_malformed_response_non_retryable(self):
        c, t = _client({"get_document": sx.FakeResponse(200, malformed=True)})
        with self.assertRaises(ProviderError) as e:
            c.get_document("D1", "tok")
        self.assertEqual(e.exception.code, "scts_malformed_response")
        self.assertFalse(e.exception.retryable)

    def test_bulk_process_sends_expected_body(self):
        c, t = _client({"bulk_process": sx.bulk_ok("TXN9")})
        c.bulk_process(["D1", "D2"], "U1", "SIG-U1", 5, "tok")
        body = t.last_body("bulk_process")
        self.assertEqual(body["instanceIds"], ["D1", "D2"])
        self.assertEqual(body["userId"], "U1")
        self.assertEqual(body["signatureId"], "SIG-U1")
        self.assertEqual(body["transitionType"], 5)

    def test_document_404_maps_not_found(self):
        c, t = _client({"get_document": sx.FakeResponse(404, {})})
        with self.assertRaises(ProviderError) as e:
            c.get_document("NOPE", "tok")
        self.assertEqual(e.exception.code, "scts_document_not_found")


def _adapter(script):
    t = sx.FakeTransport(script)
    ad = sx.make_adapter(t)
    ad._password = lambda field: {"password": "pw", "token_cache": "tok"}.get(field)
    ad._store_token = lambda *a, **k: None
    ad._cached_token = lambda: None  # force fresh login through the fake transport
    return ad, t


class TestSctsAdapter(FrappeTestCase):
    def test_authenticate_and_token_refresh(self):
        ad, t = _adapter({"login": sx.login_ok("tok", 60)})
        out = ad.authenticate()
        self.assertTrue(out["authenticated"])
        self.assertEqual(ad.refresh_or_get_token(), "tok")

    def test_login_without_token_raises(self):
        ad, t = _adapter({"login": sx.FakeResponse(200, {"expiresInMinutes": 10})})
        with self.assertRaises(ProviderError) as e:
            ad.authenticate()
        self.assertEqual(e.exception.code, "scts_login_no_token")

    def test_list_user_signatures_normalized(self):
        ad, t = _adapter({"login": sx.login_ok(), "get_signatures": sx.signatures_for("U1")})
        sigs = ad.list_user_signatures("U1")
        self.assertEqual(sigs[0]["id"], "SIG-U1")
        self.assertEqual(sigs[0]["signerId"], "U1")
        self.assertTrue(sigs[0]["active"])

    def test_validate_signature_owner_ok(self):
        ad, t = _adapter({"login": sx.login_ok(),
                          "get_signatures": sx.signatures_for("U1", "SIG-U1", active=True)})
        self.assertTrue(ad.validate_signature_owner("U1", "SIG-U1").ok)

    def test_validate_signature_owner_foreign_signature_blocked(self):
        ad, t = _adapter({"login": sx.login_ok(),
                          "get_signatures": sx.signatures_for("U1", "SIG-U1")})
        vr = ad.validate_signature_owner("U1", "SIG-OTHER")
        self.assertFalse(vr.ok)
        self.assertEqual(vr.reason, "signature_not_in_user_set")

    def test_validate_signature_owner_inactive_blocked(self):
        ad, t = _adapter({"login": sx.login_ok(),
                          "get_signatures": sx.signatures_for("U1", "SIG-U1", active=False)})
        vr = ad.validate_signature_owner("U1", "SIG-U1")
        self.assertFalse(vr.ok)
        self.assertEqual(vr.reason, "signature_inactive")

    def test_single_relogin_on_401_then_success(self):
        # first get_signatures 401 -> adapter re-logins once -> retry succeeds
        ad, t = _adapter({"login": [sx.login_ok("tok1"), sx.login_ok("tok2")],
                          "get_signatures": [sx.FakeResponse(401, {}), sx.signatures_for("U1")]})
        sigs = ad.list_user_signatures("U1")
        self.assertEqual(sigs[0]["signerId"], "U1")
        self.assertEqual(t.count("login"), 2)  # exactly one re-login
        self.assertEqual(t.count("get_signatures"), 2)

    def test_approve_and_sign_extracts_txn_id(self):
        ad, t = _adapter({"login": sx.login_ok(), "bulk_process": sx.bulk_ok("TXN-77")})
        out = ad.approve_and_sign(["D1"], "U1", "SIG-U1")
        self.assertEqual(out["bulk_job_transaction_id"], "TXN-77")

    def test_poll_status_signed_normalized(self):
        ad, t = _adapter({"login": sx.login_ok(),
                          "get_document": sx.document("D1", "U1", "SIG-U1", status="signed")})
        st = ad.poll_status("D1")
        self.assertEqual(st.document_id, "D1")
        s = st.signer("U1")
        self.assertEqual(s["status"], "signed")
        self.assertEqual(s["signature_id"], "SIG-U1")
        self.assertEqual(len(st.files), 2)

    def test_poll_status_rejected_and_pending_variants(self):
        ad, t = _adapter({"login": sx.login_ok(),
                          "get_document": sx.document("D1", "U1", "SIG-U1", status="declined")})
        self.assertEqual(ad.poll_status("D1").signer("U1")["status"], "rejected")
        ad2, t2 = _adapter({"login": sx.login_ok(),
                            "get_document": sx.document("D2", "U1", "SIG-U1", status="pending")})
        self.assertEqual(ad2.poll_status("D2").signer("U1")["status"], "pending")

    def test_deferred_ops_fail_closed(self):
        ad, t = _adapter({"login": sx.login_ok()})
        for fn in (lambda: ad.create_document({}),
                   lambda: ad.get_pdf("D1", "F1"),
                   lambda: ad.execute_transition("D1", -16)):
            with self.assertRaises(ProviderError) as e:
                fn()
            self.assertFalse(e.exception.retryable)
