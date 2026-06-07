"""Phase D tests - no-write enforcement + normalizer golden file + guards.
Bench run:
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_d
The TestNoWrite + TestNormalizer classes are also runnable WITHOUT a site
(pure logic; frappe stubbed by conftest-style import guard below if needed).
"""
import json
import os
import re
import unittest

import frappe

from ecentric_workspace.alerts.services import dedupe_keys
from ecentric_workspace.alerts.services import omisell_client as oc
from ecentric_workspace.alerts.services import omisell_normalizer as norm

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "omisell_order_detail.json")
WRITE_VERBS = re.compile(r"(adjust|update|cancel|delete|delist|create_product|"
                         r"set_stock|buffer|webhook|patch|put)", re.I)


class TestNoWrite(unittest.TestCase):
    """Decision: Phase D has NO Omisell write path. Proven here."""

    def test_allowed_methods_frozen_get_only(self):
        self.assertEqual(oc.ALLOWED_METHODS, frozenset({"GET"}))
        self.assertIsInstance(oc.ALLOWED_METHODS, frozenset)

    def test_public_surface_has_no_mutation_functions(self):
        public = [n for n in dir(oc.OmisellClient) if not n.startswith("_")]
        self.assertEqual(sorted(public),
                         ["get_order_detail", "get_orders", "get_shops"])
        for n in dir(oc):
            if callable(getattr(oc, n)) and not n.startswith("_"):
                self.assertIsNone(WRITE_VERBS.search(n), n)

    def test_chokepoint_refuses_write_verbs(self):
        client = oc.OmisellClient.__new__(oc.OmisellClient)  # no DB needed
        client.base = "https://api.omisell.com"
        client.bis = None
        client.last_rate_header = None
        client._last_call = 0.0
        for method, path in (
            ("POST", "/api/v2/public/order/list"),
            ("POST", "/api/v2/public/inventory/adjust"),
            ("PATCH", "/api/v2/public/order/x"),
            ("PUT", "/api/v2/public/product/x"),
            ("DELETE", "/api/v2/public/anything"),
        ):
            with self.assertRaises(Exception, msg="%s %s must be refused" % (method, path)):
                client._request(method, path, auth=(method != "POST"))

    def test_auth_post_only_on_allowlisted_path(self):
        client = oc.OmisellClient.__new__(oc.OmisellClient)
        client.base = "https://api.omisell.com"
        client.bis = None
        client.last_rate_header = None
        client._last_call = 0.0
        # POST to a NON-auth path with auth=False must still be refused
        with self.assertRaises(Exception):
            client._request("POST", "/api/v2/public/order/list", auth=False)

    def test_auth_post_body_contains_both_credentials(self):
        """Hotfix 2026-06-08: official contract = POST /api/v2/auth/token/get/
        with JSON body {api_key, api_secret} - BOTH from BIS."""
        client = oc.OmisellClient.__new__(oc.OmisellClient)

        class BisStub:
            name = "BIS-TEST"
            token_expired_at = None
            def get_password(self, field, raise_exception=True):
                return {"api_key": "K", "api_secret": "S"}.get(field)
            def save(self, **kw):
                pass
        client.bis = BisStub()
        client.base = "https://api.omisell.com"
        client.last_rate_header = None
        client._last_call = 0.0
        captured = {}

        def fake_request(method, path, params=None, json_body=None, auth=True):
            captured.update({"method": method, "path": path,
                             "json_body": json_body, "auth": auth})
            return {"data": {"token": "T", "expired_time": 1765200000}}
        client._request = fake_request
        token = client._authenticate()
        self.assertEqual(token, "T")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], oc.DEFAULT_AUTH_PATH)
        self.assertEqual(captured["json_body"],
                         {"api_key": "K", "api_secret": "S"})
        self.assertFalse(captured["auth"])

    def test_auth_default_path_is_official(self):
        self.assertEqual(oc.DEFAULT_AUTH_PATH, "/api/v2/auth/token/get/")

    def test_auth_requires_both_credentials(self):
        client = oc.OmisellClient.__new__(oc.OmisellClient)

        class BisStub:
            name = "BIS-TEST"
            token_expired_at = None
            def get_password(self, field, raise_exception=True):
                return {"api_key": "K"}.get(field)  # api_secret missing
        client.bis = BisStub()
        client.base = "https://api.omisell.com"
        client.last_rate_header = None
        client._last_call = 0.0
        with self.assertRaises(Exception):
            client._authenticate()

    def test_sanitize_strips_credentials(self):
        dirty = {"token": "x", "data": {"api_key": "y", "refresh_token": "z",
                                        "results": [{"authorization": "a", "ok": 1}]}}
        clean = oc.sanitize(dirty)
        flat = json.dumps(clean)
        for secret in ("\"x\"", "\"y\"", "\"z\"", "\"a\""):
            self.assertNotIn(secret, flat)
        self.assertIn("\"ok\": 1", flat)

    def test_only_client_module_imports_http(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for root, _dirs, files in os.walk(base):
            if "__pycache__" in root:
                continue
            for fn in files:
                if not fn.endswith(".py") or fn == "omisell_client.py":
                    continue
                src = open(os.path.join(root, fn), encoding="utf-8").read()
                if re.search(r"^\s*import requests|^\s*from requests", src, re.M):
                    offenders.append(fn)
        self.assertEqual(offenders, [])


class TestNormalizer(unittest.TestCase):
    def setUp(self):
        self.data = json.load(open(GOLDEN, encoding="utf-8"))

    def test_golden_mapping(self):
        o = norm.normalize_order_detail(self.data)
        self.assertEqual(o["external_order_id"], "OMI-GOLD-0001")
        self.assertEqual(o["platform"], "Shopee")
        self.assertEqual(o["omisell_shop_id"], "12345")
        self.assertEqual(len(o["items"]), 2)
        a, b = o["items"]
        self.assertEqual(a["external_line_id"], "PKG-1:GOLD-SKU-A")
        self.assertEqual(a["unit_check_price"], 99000.0)       # Q-D5 provisional
        self.assertEqual(a["seller_discount"], 16000.0)        # discount+voucher seller
        self.assertEqual(a["platform_discount"], 5000.0)
        self.assertIsNone(a["customer_paid_price"])
        self.assertEqual(b["external_line_id"], "PKG-1:GOLD-SKU-B")
        self.assertEqual(b["unit_check_price"], 9900.0)

    def test_line_ids_stable_across_parses(self):
        o1 = norm.normalize_order_detail(self.data)
        o2 = norm.normalize_order_detail(json.loads(json.dumps(self.data)))
        self.assertEqual([l["external_line_id"] for l in o1["items"]],
                         [l["external_line_id"] for l in o2["items"]])

    def test_status_filter_keywords(self):
        self.assertTrue(norm.is_real_sale(12, "Delivered")[0])
        self.assertTrue(norm.is_real_sale(5, "Ready to Ship")[0])
        self.assertFalse(norm.is_real_sale(20, "Cancelled")[0])
        self.assertFalse(norm.is_real_sale(1, "Draft")[0])
        ok, reason = norm.is_real_sale(99, "Mystery Status")
        self.assertFalse(ok)                       # unknown -> conservative exclude
        self.assertEqual(reason, "unknown_status")

    def test_dedupe_key_q_d3(self):
        self.assertEqual(dedupe_keys.ingestion_failed_key("BBT-VN", "20260608"),
                         "omisell|BBT-VN|ingestion_api_failed|20260608")


class TestEndpointGuards(unittest.TestCase):
    """Needs a bench site (frappe session)."""

    def test_non_sm_denied_everywhere(self):
        if not getattr(frappe, "session", None) or not getattr(frappe.session, "user", None):
            self.skipTest("needs bench site")
        from ecentric_workspace.alerts import api_omisell
        user = "alerte.nobody@example.com"
        if not frappe.db.exists("User", user):
            frappe.get_doc({"doctype": "User", "email": user, "first_name": "n",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        frappe.set_user(user)
        try:
            for fn, kw in ((api_omisell.omisell_probe, {"brand": "X"}),
                           (api_omisell.sync_shop_directory, {"brand": "X"}),
                           (api_omisell.pull_one_order, {"brand": "X", "omisell_order_number": "Y"}),
                           (api_omisell.pull_orders, {"brand": "X", "updated_from": "2026-06-08 00:00:00",
                                                      "updated_to": "2026-06-08 00:30:00"})):
                with self.assertRaises(frappe.PermissionError):
                    fn(**kw)
        finally:
            frappe.set_user("Administrator")

    def test_window_guard_3600s(self):
        if not getattr(frappe, "session", None) or not getattr(frappe.session, "user", None):
            self.skipTest("needs bench site")
        from ecentric_workspace.alerts import api_omisell
        frappe.set_user("Administrator")
        with self.assertRaises(Exception):
            api_omisell.pull_orders("NO-BRAND", "2026-06-08 00:00:00", "2026-06-08 01:00:01")
