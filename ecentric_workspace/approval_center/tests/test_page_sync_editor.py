# Copyright (c) 2026, eCentric and contributors
"""PR#148 UI wiring: the placement editor is injected into the PR page exactly once
(idempotent), EC_PPH_CONFIG comes from the governed backend endpoint, and the governed desk
pages exist with the right role restriction. Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_page_sync_editor
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import api
from ecentric_workspace.approval_center.payment_request import page_sync
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestPageSyncEditor(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_editor_injected_exactly_once_and_idempotent(self):
        html1 = page_sync._html()
        html2 = page_sync._html()          # rebuilt from source each time
        self.assertEqual(html1.count('id="ec-pph-editor"'), 1)
        self.assertEqual(html1.count('id="ec-pph-coords"'), 1)
        self.assertEqual(html1, html2)      # idempotent

    def test_coords_loaded_before_editor(self):
        html = page_sync._html()
        self.assertLess(html.index('id="ec-pph-coords"'), html.index('id="ec-pph-editor"'))

    def test_no_cdn_or_raw_private_file_url(self):
        html = page_sync._html()
        for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis", "/private/files/"):
            self.assertNotIn(bad, html)
        self.assertIn("/assets/ecentric_workspace/esign/coords.js", html)

    def test_config_from_backend_state(self):
        h = fx.full_stack(fx.PFX + "pe1r@example.com", fx.PFX + "pe1m@example.com")
        frappe.set_user(h["mgr"])
        cfg = api.placement_editor_config(h["biz"])
        frappe.set_user("Administrator")
        self.assertIn("package", cfg)
        self.assertIn("files", cfg)
        self.assertIn("locked", cfg)

    def test_governed_pages_exist_with_roles(self):
        self.assertTrue(frappe.db.exists("Page", "ec-signing-inbox"))
        self.assertTrue(frappe.db.exists("Page", "ec-uat-pilot-panel"))
        roles = frappe.get_all("Has Role", filters={"parent": "ec-uat-pilot-panel"},
                               pluck="role")
        self.assertIn("System Manager", roles)   # control panel is SM-only
