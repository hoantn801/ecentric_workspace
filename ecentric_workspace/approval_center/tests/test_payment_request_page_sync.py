# Copyright (c) 2026, eCentric and contributors
"""Runtime tests for payment_request/page_sync.py (PR#146 restore). Compile is not
enough: these prove the module imports, ALL four functions exist and are callable, the
_html() output wires the e-sign panel exactly once while preserving the original main
section, sync() still uses the shared upsert path, and the System Manager guard holds.
An ast parse of the source fails if the file was truncated to a valid-but-wrong tail
(e.g. `retur`).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_payment_request_page_sync
"""
import ast
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.payment_request import page_sync


class TestPaymentRequestPageSync(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_all_four_functions_exist_in_source(self):
        # parses the on-disk source; a truncated file (missing sync/…) fails here even
        # though a partial file might still import.
        src = open(page_sync.__file__.replace(".pyc", ".py"), encoding="utf-8").read()
        names = {n.name for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.FunctionDef)}
        self.assertEqual({"_esign_panel", "_html", "sync", "sync_payment_request_page"}
                         <= names, True, "missing functions (truncation?): %s" % names)

    def test_callables(self):
        for fn in ("_esign_panel", "_html", "sync", "sync_payment_request_page"):
            self.assertTrue(callable(getattr(page_sync, fn)), fn)

    def test_html_returns_string_with_panel_once_and_original_marker(self):
        html = page_sync._html()
        self.assertIsInstance(html, str)
        self.assertEqual(html.count('id="ec-esign-panel"'), 1)  # panel wired exactly once
        self.assertIn('id="ec-payr-root"', html)  # original PR main section preserved
        self.assertIn('id="ec-payment-request"', html)

    def test_sync_uses_shared_upsert_path(self):
        with patch.object(page_sync.page_sync_util, "upsert_web_page",
                          return_value={"name": None}) as up:
            page_sync.sync()
        self.assertEqual(up.call_count, 1)
        args = up.call_args[0]
        self.assertEqual((args[0], args[1], args[2]),
                         (page_sync.ROUTE, page_sync.NAME, page_sync.TITLE))
        self.assertIn('id="ec-esign-panel"', args[3])  # the synced HTML carries the panel

    def test_system_manager_guard_intact(self):
        u = "zz_ps_nonsm@example.com"
        if not frappe.db.exists("User", u):
            frappe.get_doc({"doctype": "User", "email": u, "first_name": "PS",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        frappe.set_user(u)
        with self.assertRaises(frappe.PermissionError):
            page_sync.sync_payment_request_page()
        frappe.set_user("Administrator")
