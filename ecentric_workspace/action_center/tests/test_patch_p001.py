# Copyright (c) 2026, eCentric and contributors
"""Tests for p001_homepage_action_center patch.

We test the patch logic directly without depending on a real homepage Web
Page: we create a temporary Web Page with the exact OLD markers, run the
patch, and assert the new content. We then re-run to assert idempotency,
and run on a marker-less page to assert fail-loud.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.action_center.patches import (
    p001_homepage_action_center as p001,
)

TMP_WP_NAME = "ac-test-fake-home"
TMP_WP_ROUTE = "ac-test-home"


def _baseline_main_section():
    """A minimal main_section containing both OLD markers + dummy widget body."""
    return (
        '<div class="panel">'
        '  <div class="panel-header">'
        '    <div class="panel-title">Chờ phê duyệt</div>'
        '  </div>'
        '  <div class="approval-list"></div>'
        '</div>'
        '<script id="ec-home-todo-widget">'
        '// fake old widget body\n'
        '(function(){})();\n'
        '</script><!-- /ec-home-todo-widget -->'
    )


def _make_wp(name, route, main_section):
    if frappe.db.exists("Web Page", name):
        wp = frappe.get_doc("Web Page", name)
        wp.main_section = main_section
        wp.main_section_html = main_section
        wp.route = route
        wp.published = 0
        wp.save(ignore_permissions=True)
        return wp
    wp = frappe.get_doc({
        "doctype": "Web Page", "title": name, "name": name,
        "route": route, "published": 0,
        "main_section": main_section, "main_section_html": main_section,
    })
    wp.insert(ignore_permissions=True)
    return wp


class TestP001PatchIdempotentAndFailLoud(FrappeTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if frappe.db.exists("Web Page", TMP_WP_NAME):
            frappe.delete_doc("Web Page", TMP_WP_NAME,
                ignore_permissions=True, force=True)

    def _run_with_test_wp(self):
        """Monkey-patch p001._resolve_wp_name to return our temporary Web Page."""
        orig = p001._resolve_wp_name
        p001._resolve_wp_name = lambda: TMP_WP_NAME
        try:
            p001.execute()
        finally:
            p001._resolve_wp_name = orig

    def test_happy_path_replaces_title_and_widget(self):
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, _baseline_main_section())
        self._run_with_test_wp()
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        main = wp.main_section
        self.assertIn('Việc cần làm', main)
        self.assertNotIn('Chờ phê duyệt', main)
        self.assertIn('<script id="ec-action-center-widget">', main)
        self.assertNotIn('<script id="ec-home-todo-widget">', main)
        # New widget MUST call the new endpoint, not the old one.
        self.assertIn(
            "ecentric_workspace.action_center.api.get_action_items", main)
        self.assertNotIn("gbs_user_pending_todos", main)
        # Cache-bust: main_section_html should match too.
        self.assertEqual(wp.main_section, wp.main_section_html)

    def test_rerun_is_idempotent_noop(self):
        # Already migrated from previous test (or migrate now).
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, _baseline_main_section())
        self._run_with_test_wp()
        wp_after_1st = frappe.get_doc("Web Page", TMP_WP_NAME).main_section
        # Run again -> should be no-op.
        self._run_with_test_wp()
        wp_after_2nd = frappe.get_doc("Web Page", TMP_WP_NAME).main_section
        self.assertEqual(wp_after_1st, wp_after_2nd)

    def test_missing_old_marker_fails_loud(self):
        # Web Page without the required OLD markers -> patch must throw,
        # NOT silently mutate.
        broken = '<div class="panel"><div class="panel-title">Some Other Card</div></div>'
        _make_wp(TMP_WP_NAME, TMP_WP_ROUTE, broken)
        with self.assertRaises(frappe.ValidationError):
            self._run_with_test_wp()
        # And: nothing got written.
        wp = frappe.get_doc("Web Page", TMP_WP_NAME)
        self.assertEqual(wp.main_section, broken)
        self.assertNotIn("ec-action-center-widget", wp.main_section)
