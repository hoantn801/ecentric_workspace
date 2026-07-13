# Copyright (c) 2026, eCentric and contributors
"""SCTS login-contract tests (fix/scts-login-contract). Pure/frappe-free (injected
transport, no network); runs in any Python and under bench run-tests. Proves the exact
confirmed SCTS body {"Site","Username","Password"}, blank-Site fail-closed before network,
sanitized 4xx, and token/expiry passthrough."""
import unittest

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient


class _Resp(object):
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = str(payload)

    def json(self):
        return self._p


class _Capture(object):
    def __init__(self, resp=None, exc=None):
        self.resp = resp
        self.exc = exc
        self.calls = []

    def __call__(self, method, url, headers=None, json_body=None, timeout=30, verify_tls=True):
        self.calls.append({"method": method, "url": url, "body": json_body,
                           "headers": dict(headers or {})})
        if self.exc:
            raise self.exc
        return self.resp


def _client(cap):
    return SctsClient("https://scts.uat.local", timeout=5, retry_limit=0,
                      transport=cap, sleeper=lambda *_: None)


class TestSctsLoginContract(unittest.TestCase):
    def test_exact_body_keys_and_casing(self):
        cap = _Capture(_Resp(200, {"token": "t", "expiresInMinutes": 60}))
        _client(cap).login("eCentric", "alice", "secret")
        body = cap.calls[0]["body"]
        self.assertEqual(set(body.keys()), {"Site", "Username", "Password"})
        self.assertEqual(body["Site"], "eCentric")
        self.assertEqual(body["Username"], "alice")
        self.assertEqual(body["Password"], "secret")

    def test_site_is_included(self):
        cap = _Capture(_Resp(200, {"token": "t"}))
        _client(cap).login("eCentric", "u", "p")
        self.assertIn("Site", cap.calls[0]["body"])

    def test_lowercase_keys_absent(self):
        cap = _Capture(_Resp(200, {"token": "t"}))
        _client(cap).login("eCentric", "u", "p")
        for k in ("site", "username", "password"):
            self.assertNotIn(k, cap.calls[0]["body"])

    def test_blank_site_rejected_before_network(self):
        cap = _Capture(_Resp(200, {"token": "t"}))
        with self.assertRaises(ProviderError) as e:
            _client(cap).login("", "u", "p")
        self.assertEqual(e.exception.code, "scts_site_missing")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(len(cap.calls), 0)   # no network call

    def test_http_400_sanitized_non_retryable(self):
        cap = _Capture(_Resp(400, {"error": "bad request"}))
        with self.assertRaises(ProviderError) as e:
            _client(cap).login("eCentric", "u", "SuperSecretPw")
        self.assertEqual(e.exception.code, "scts_auth_failed")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(len(cap.calls), 1)   # 4xx never retried
        msg = str(e.exception)
        self.assertNotIn("SuperSecretPw", msg)   # password never leaked
        self.assertNotIn("Password", msg)

    def test_login_success_returns_payload_with_token_and_expiry(self):
        cap = _Capture(_Resp(200, {"token": "jwt-uat", "expiresInMinutes": 525600}))
        out = _client(cap).login("eCentric", "u", "p")
        self.assertEqual(out["token"], "jwt-uat")
        self.assertEqual(out["expiresInMinutes"], 525600)

    def test_url_is_governed_login_endpoint(self):
        cap = _Capture(_Resp(200, {"token": "t"}))
        _client(cap).login("eCentric", "u", "p")
        self.assertTrue(cap.calls[0]["url"].endswith("/api/Auth/login"))


if __name__ == "__main__":
    unittest.main()
