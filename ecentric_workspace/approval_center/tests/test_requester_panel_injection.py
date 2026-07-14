# Copyright (c) 2026, eCentric and contributors
"""Requester signing panel is injected into the PR page exactly once and idempotently
(fix/scts-requester-package-entrypoint UI). DOM behaviour (visibility/prepare/lock) is
verified in PR CI jsdom / UAT; here we assert governed injection + no CDN/raw URL. Runs on
the bench: bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_panel_injection
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.payment_request import page_sync


class TestRequesterPanelInjection(FrappeTestCase):
    def test_requester_panel_injected_once_idempotent(self):
        h1 = page_sync._html()
        h2 = page_sync._html()
        self.assertEqual(h1.count('id="ec-req-sign"'), 1)
        self.assertEqual(h1.count('id="ec-req-sign-script"'), 1)
        self.assertEqual(h1, h2)

    def test_panel_calls_governed_endpoints_only(self):
        html = page_sync._html()
        self.assertIn("esign.api.prepare_requester_signing_package", html)
        self.assertIn("esign.api.requester_lock_signing_package", html)
        self.assertIn("esign.api.requester_signing_readiness", html)

    def test_no_cdn_or_raw_private_file_url(self):
        html = page_sync._html()
        for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis", "/private/files/"):
            self.assertNotIn(bad, html)

    def test_editor_panel_still_present(self):
        # existing approver placement editor flow preserved
        html = page_sync._html()
        self.assertIn('id="ec-pph-editor"', html)
        # requester panel appears before the editor
        self.assertLess(html.index('id="ec-req-sign"'), html.index('id="ec-pph-editor"'))
