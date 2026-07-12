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


if __name__ == "__main__":
    unittest.main()
