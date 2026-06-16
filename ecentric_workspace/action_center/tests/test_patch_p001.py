# Copyright (c) 2026, eCentric and contributors
"""Tests for p001_homepage_action_center (hardened version)."""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.action_center.patches import (
    p001_homepage_action_center as p001,
)

TMP_WP_NAME = "ac-test-fake-home"
TMP_WP_ROUTE = "ac-test-home"


def _legacy_main_section():
    return (
        '<div class="panel">'
        '  <div class="panel-header">'
        '    <div class="panel-title">Chờ phê duyệt</div>'
        '  </div>'
        '  <div class="approval-list"></div>'
        '</div>'
        '<script id="ec-home-todo-widget">'
        '// fake old widget body\n'
        '</script><!-- /ec-home-todo-widget -->'
    )


def _make_wp(name, route, main, html=None):
    if frappe.db.exists("Web Page", name):
        wp = frappe.get_doc("Web Page", name)
    else:
        wp = frappe.get_doc({
            "doctype": "Web Page", "title": name, "name": name,
            "route": route, "published": 0,
        })
        wp.insert(ignore_permissions=True)
    wp.main_section = main
    wp.main_section_html = html if html is not None else main
    wp.save(ignore_permissions=True)
    return wp


def _run_with_test_wp():
    orig = p001._resolve_wp_name
    p001._resolve_wp_name = lambda: TMP_WP_NAME
    try:
        p001.execute()
    finally:
        p001._resolve_wp_name = orig


class TestP001Patch(FrappeTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if frappe.db.exists("Web Page", TMP_WP_NAME):
            frappe.delete_doc("Web Page", TMP_WP_NAME,
                ignore_permissions=True, force=True)

    # ---- happy path -------------------------------------------------------

    def test_happy_path_replaces_title_and_inserts_loader(self):
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, _legacy_main_section())
        _run_with_test_wp()
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        for field in ("main_section", "main_section_html"):
            body = getattr(wp, field) or ""
            self.assertIn('Việc cần làm', body)
            self.assertNotIn('Chờ phê duyệt', body)
            # Loader script tag, NOT inline widget body.
            self.assertIn(
                '<script id="ec-action-center-widget"', body)
            self.assertIn(
                '/assets/ecentric_workspace/js/action_center_widget.js', body)
            # Old widget id must be gone.
            self.assertNotIn('<script id="ec-home-todo-widget">', body)
            # The legacy /approval URL builder MUST be gone.
            self.assertNotIn("'/approval?id='", body)
            self.assertNotIn("gbs_user_pending_todos", body)

    # ---- idempotency ------------------------------------------------------

    def test_rerun_is_idempotent_noop(self):
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, _legacy_main_section())
        _run_with_test_wp()
        after_1 = frappe.get_doc("Web Page", TMP_WP_NAME).main_section
        _run_with_test_wp()
        after_2 = frappe.get_doc("Web Page", TMP_WP_NAME).main_section
        self.assertEqual(after_1, after_2)

    # ---- fail-loud --------------------------------------------------------

    def test_missing_old_markers_fails_loud_no_mutation(self):
        broken = '<div class="panel"><div class="panel-title">Other</div></div>'
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, broken)
        with self.assertRaises(frappe.ValidationError):
            _run_with_test_wp()
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        # Untouched.
        self.assertEqual(wp.main_section, broken)
        self.assertNotIn("ec-action-center-widget", wp.main_section)

    def test_diverging_legacy_fields_fails_loud(self):
        """If main_section and main_section_html both look legacy but
        differ, the patch must refuse to mutate."""
        a = _legacy_main_section()
        b = _legacy_main_section() + "<!-- extra -->"
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, a, html=b)
        with self.assertRaises(frappe.ValidationError):
            _run_with_test_wp()
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        self.assertEqual(wp.main_section, a)
        self.assertEqual(wp.main_section_html, b)

    def test_unknown_state_field_fails_loud(self):
        """One field already migrated, the other in an unknown state ->
        refuse to mutate."""
        migrated = _legacy_main_section().replace(
            '<script id="ec-home-todo-widget">',
            p001.NEW_WIDGET_MARKER + ' src="/x.js" defer></script><!-- legacy-stub'
        )
        weird = "<div>Something totally different</div>"
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, migrated, html=weird)
        with self.assertRaises(frappe.ValidationError):
            _run_with_test_wp()

    # ---- partial state ----------------------------------------------------

    def test_only_main_section_has_legacy_only_that_field_updated(self):
        """When the legacy widget is only in main_section, only that field
        is mutated. main_section_html stays empty."""
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, _legacy_main_section(), html="")
        _run_with_test_wp()
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        self.assertIn(p001.NEW_WIDGET_MARKER, wp.main_section)
        # The html field stays empty (we never touch an empty field).
        self.assertEqual(wp.main_section_html, "")

    # ---- asset present ----------------------------------------------------

    def test_asset_file_exists_in_repo(self):
        """The loader points at /assets/ecentric_workspace/js/
        action_center_widget.js. Verify the source file exists in the repo
        so the patch's HTML reference does not point at a 404."""
        # Resolve repo path relative to the patch module.
        patch_path = os.path.dirname(os.path.dirname(
            os.path.dirname(p001.__file__)))
        asset = os.path.join(patch_path, "public", "js",
            "action_center_widget.js")
        self.assertTrue(os.path.exists(asset),
            "Asset missing at: " + asset)

    def test_asset_uses_frappe_call_not_raw_fetch(self):
        """Regression: the asset must use frappe.call, not raw fetch(POST)."""
        patch_path = os.path.dirname(os.path.dirname(
            os.path.dirname(p001.__file__)))
        asset = os.path.join(patch_path, "public", "js",
            "action_center_widget.js")
        with open(asset) as f:
            src = f.read()
        self.assertIn("frappe.call", src)
        self.assertIn(
            "ecentric_workspace.action_center.api.get_action_items", src)
        # No raw POST + manual CSRF body to the new endpoint.
        self.assertNotIn(
            "fetch('/api/method/ecentric_workspace.action_center", src)

    def test_asset_does_not_build_approval_url(self):
        """Regression: the asset must NOT contain any /approval URL builder."""
        patch_path = os.path.dirname(os.path.dirname(
            os.path.dirname(p001.__file__)))
        asset = os.path.join(patch_path, "public", "js",
            "action_center_widget.js")
        with open(asset) as f:
            src = f.read()
        self.assertNotIn("/approval?id=", src)
        self.assertNotIn('+ "&type="', src)
