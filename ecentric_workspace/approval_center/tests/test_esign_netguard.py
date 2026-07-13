# Copyright (c) 2026, eCentric and contributors
"""SSRF / provider-URL safety tests (Phase 8). Frappe-free, deterministic."""
import unittest

from ecentric_workspace.approval_center.esign import netguard as N


class TestNetguard(unittest.TestCase):
    def test_https_public_host_ok(self):
        ok, reason = N.validate_base_url("https://scts.uat.example.vn/api")
        self.assertTrue(ok, reason)

    def test_http_rejected(self):
        ok, reason = N.validate_base_url("http://scts.uat.example.vn")
        self.assertFalse(ok)
        self.assertEqual(reason, "scheme_not_https")

    def test_embedded_credentials_rejected(self):
        ok, reason = N.validate_base_url("https://user:pass@scts.example.vn")
        self.assertFalse(ok)
        self.assertEqual(reason, "embedded_credentials")

    def test_loopback_and_private_rejected(self):
        for u in ("https://localhost/api", "https://127.0.0.1", "https://10.0.0.5",
                  "https://192.168.1.9", "https://169.254.169.254/latest"):
            ok, _ = N.validate_base_url(u)
            self.assertFalse(ok, u)

    def test_cloud_metadata_hostname_rejected(self):
        ok, reason = N.validate_base_url("https://metadata.google.internal")
        self.assertFalse(ok)

    def test_allowlist_pins_host(self):
        ok, _ = N.validate_base_url("https://evil.example.com", allow_hosts={"scts.uat.vn"})
        self.assertFalse(ok)
        ok, _ = N.validate_base_url("https://scts.uat.vn", allow_hosts={"scts.uat.vn"})
        self.assertTrue(ok)

    def test_empty_and_malformed(self):
        self.assertFalse(N.validate_base_url("")[0])
        self.assertFalse(N.validate_base_url("not a url")[0])

    def test_safe_join_blocks_override_and_traversal(self):
        with self.assertRaises(ValueError):
            N.safe_join("https://x", "http://evil")
        with self.assertRaises(ValueError):
            N.safe_join("https://x", "/api/../../secret")
        self.assertEqual(N.safe_join("https://x/", "/api/AddDocument"),
                         "https://x/api/AddDocument")

    def test_assert_raises_on_unsafe(self):
        with self.assertRaises(ValueError):
            N.assert_base_url_safe("http://127.0.0.1")


    def test_empty_allowlist_fails_closed_when_required(self):
        ok, reason = N.validate_base_url("https://scts.uat.vn", require_allowlist=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "empty_allowlist_fail_closed")
        ok2, _ = N.validate_base_url("https://scts.uat.vn", allow_hosts=["scts.uat.vn"],
                                     require_allowlist=True)
        self.assertTrue(ok2)

    def test_resolve_public_ok_private_blocked(self):
        self.assertTrue(N.resolve_and_validate("scts.vn", resolver=lambda h: ["8.8.8.8"])[0])
        self.assertFalse(N.resolve_and_validate("scts.vn", resolver=lambda h: ["10.0.0.5"])[0])
        self.assertFalse(N.resolve_and_validate("scts.vn", resolver=lambda h: ["127.0.0.1"])[0])

    def test_resolve_rebinding_mixed_blocked(self):
        ok, reason, _ = N.resolve_and_validate(
            "scts.vn", resolver=lambda h: ["8.8.8.8", "127.0.0.1"])
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("resolves_to_blocked"))

    def test_resolve_literal_private_ip_blocked(self):
        self.assertFalse(N.resolve_and_validate("10.0.0.9")[0])

    def test_dns_failure_fails_closed(self):
        ok, reason, _ = N.resolve_and_validate(
            "scts.vn", resolver=lambda h: (_ for _ in ()).throw(OSError()))
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("dns_resolution_failed"))

    def test_assert_request_allowed_requires_allowlist_and_dns(self):
        with self.assertRaises(ValueError):
            N.assert_request_allowed("https://scts.vn", [], resolver=lambda h: ["8.8.8.8"])
        self.assertTrue(N.assert_request_allowed(
            "https://scts.vn", ["scts.vn"], resolver=lambda h: ["8.8.8.8"]))
        with self.assertRaises(ValueError):
            N.assert_request_allowed("https://scts.vn", ["scts.vn"],
                                     resolver=lambda h: ["10.0.0.5"])


if __name__ == "__main__":
    unittest.main()
