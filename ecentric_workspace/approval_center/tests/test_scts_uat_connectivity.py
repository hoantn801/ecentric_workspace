# Copyright (c) 2026, eCentric and contributors
"""OPT-IN SCTS UAT connectivity smoke test. This is the ONLY test that talks to the real
SCTS UAT endpoint; it is SKIPPED unless explicitly enabled, so it never runs in CI or in
a normal `run-tests` sweep.

Enable by setting BOTH:
  * site_config / env `EC_SCTS_UAT_LIVE = 1`
  * a configured EC Digital Signature Provider Settings row (SCTS / UAT) with real
    credentials (encrypted Password fields) and integration_enabled.

It performs READ-ONLY calls (authenticate + GetSignatures for a provided user) and makes
NO signing write. Credentials come from site secrets only - never from the repo.

  EC_SCTS_UAT_LIVE=1 bench --site <site> run-tests \
      --module ecentric_workspace.approval_center.tests.test_scts_uat_connectivity
"""
import os
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase


def _live_enabled():
    if str(os.environ.get("EC_SCTS_UAT_LIVE") or "") == "1":
        return True
    try:
        return bool(int(frappe.conf.get("ec_scts_uat_live") or 0))
    except Exception:
        return False


@unittest.skipUnless(_live_enabled(),
                     "SCTS UAT live connectivity disabled (set EC_SCTS_UAT_LIVE=1 to run)")
class TestSctsUatConnectivity(FrappeTestCase):
    def _settings(self):
        s = frappe.db.get_value("EC Digital Signature Provider Settings",
                                {"provider": "SCTS", "environment": "UAT",
                                 "integration_enabled": 1}, "*", as_dict=True)
        if not s:
            self.skipTest("no enabled SCTS/UAT provider settings row configured")
        return s

    def test_authenticate_live(self):
        from ecentric_workspace.approval_center.esign.providers import get_adapter
        adapter = get_adapter(self._settings())
        out = adapter.test_connection()
        self.assertTrue(out.get("ok"))

    def test_get_signatures_live(self):
        s = self._settings()
        user_id = frappe.conf.get("ec_scts_uat_probe_user")
        if not user_id:
            self.skipTest("set site_config ec_scts_uat_probe_user to a real SCTS user id")
        from ecentric_workspace.approval_center.esign.providers import get_adapter
        sigs = get_adapter(s).list_user_signatures(user_id)
        self.assertIsInstance(sigs, list)
