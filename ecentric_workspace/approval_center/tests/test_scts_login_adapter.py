# Copyright (c) 2026, eCentric and contributors
"""SCTS adapter authenticate + verify_mapping login-contract tests. Runs on the bench (needs
frappe/DB):
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_login_adapter

Proves: authenticate reads Site from Provider Settings.site and fails closed BEFORE any
network call when Site is blank; a successful login extracts token + expiry; and
verify_mapping proceeds to GetSignatures (and marks Verified) after a successful login that
carried Site/Username/Password.
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts import SctsAdapter
from ecentric_workspace.approval_center.tests import scts_fixtures as sx

SETTINGS = "EC Digital Signature Provider Settings"


def _settings(site="eCentric"):
    name = sx.make_scts_settings()  # existing helper (UAT SCTS settings + credentials)
    frappe.db.set_value(SETTINGS, name, "site", site)
    frappe.db.set_value(SETTINGS, name, "integration_enabled", 1)
    return frappe.get_doc(SETTINGS, name)


class TestSctsLoginAdapter(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_blank_site_fails_closed_before_network(self):
        s = _settings(site="")
        t = sx.FakeTransport({"login": sx.login_ok("tok", 60)})
        ad = SctsAdapter(s, transport=t)
        with self.assertRaises(ProviderError) as e:
            ad.authenticate()
        self.assertEqual(e.exception.code, "scts_site_missing")
        self.assertEqual(t.count("login"), 0)   # never reached the network

    def test_authenticate_sends_site_and_extracts_token_expiry(self):
        s = _settings(site="eCentric")
        t = sx.FakeTransport({"login": sx.login_ok("tok-xyz", 42)})
        ad = SctsAdapter(s, transport=t)
        out = ad.authenticate()
        self.assertTrue(out["authenticated"])
        self.assertEqual(out["expires_in_minutes"], 42)
        body = [c for c in t.calls if c["key"] == "login"][0]["body"]
        self.assertEqual(set(body.keys()), {"Site", "Username", "Password"})
        self.assertEqual(body["Site"], "eCentric")

    def test_verify_mapping_proceeds_to_get_signatures_after_login(self):
        s = _settings(site="eCentric")
        # a mapping whose signature is owned by the SCTS user the GetSignatures reply returns
        mapping = frappe.get_doc({
            "doctype": "EC SCTS User Mapping", "frappe_user": "Administrator",
            "environment": "UAT", "scts_user_id": "U1", "signature_id": "SIG1",
            "active": 1, "mapping_status": "Draft"}).insert(ignore_permissions=True)
        t = sx.FakeTransport({
            "login": sx.login_ok("tok", 60),
            "get_signatures": sx.signatures_for("U1", "SIG1"),
        })
        from ecentric_workspace.approval_center.esign import api
        with patch.object(api, "get_adapter", lambda st: SctsAdapter(s, transport=t)):
            out = api.verify_mapping(mapping.name)
        self.assertTrue(out["verified"])
        self.assertEqual(t.count("login"), 1)          # authenticated first
        self.assertGreaterEqual(t.count("get_signatures"), 1)  # then GetSignatures
        self.assertEqual(frappe.db.get_value("EC SCTS User Mapping", mapping.name,
                                             "mapping_status"), "Verified")
