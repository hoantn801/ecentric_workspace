# Copyright (c) 2026, eCentric and contributors
"""Action Center resolver tests.

These exercise resolve_item + the URL builders. The Frappe-aware ones do
defensive get_value lookups; we monkey-patch frappe.db.get_value where
necessary so the tests run without specific seed data.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.action_center import resolvers


class TestActionCenterResolvers(FrappeTestCase):
    def test_build_approval_url_lowercases_and_underscores_type(self):
        # Spaces in DocType name -> underscores in `type` param.
        u = resolvers.build_approval_url("GBS Purchase Order", "GBS-PO-20260612-02710")
        self.assertIn("/approval?id=GBS-PO-20260612-02710", u)
        self.assertIn("&type=gbs_purchase_order", u)
        self.assertNotIn(" ", u)  # encoded

    def test_build_approval_url_url_encodes_name(self):
        # Names with spaces / special chars must be URL-encoded.
        u = resolvers.build_approval_url("Sales Order", "SO with space/&q")
        self.assertNotIn(" ", u)
        # Forward-slash and ampersand are part of unsafe chars -> encoded.
        self.assertIn("%20", u)
        self.assertIn("%2F", u.upper())
        self.assertIn("%26", u.upper())

    def test_build_wtu_url_encodes_label(self):
        self.assertEqual(resolvers.build_wtu_url("2026-W25"),
                         "/weekly-update?week=2026-W25")
        # Edge: a label containing whitespace must encode.
        self.assertEqual(resolvers.build_wtu_url("2026 W25"),
                         "/weekly-update?week=2026%20W25")

    def test_build_task_url_uses_app_task(self):
        self.assertEqual(resolvers.build_task_url("TASK-2026-00084"),
                         "/app/task/TASK-2026-00084")
        # Name with non-trivial chars.
        self.assertEqual(resolvers.build_task_url("TASK 100/200"),
                         "/app/task/TASK%20100%2F200")

    def test_desk_fallback_slug_uses_dashes_not_underscore_or_dot(self):
        u = resolvers.build_desk_fallback_url("Brand Approver Special", "BA-1")
        # Slug = lowercase, spaces -> dashes.
        self.assertTrue(u.startswith("/app/brand-approver-special/"))
        # Underscores ALSO collapse to dashes (Frappe slug convention).
        u2 = resolvers.build_desk_fallback_url("Some_Custom_Type", "X-1")
        self.assertTrue(u2.startswith("/app/some-custom-type/"))

    # ---- resolve_item routing ---------------------------------------------

    def test_resolve_wtu_routes_to_weekly_update(self):
        # Monkey-patch get_value to return a week label.
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            if dt == "Weekly Team Update" and field == "week_label":
                return "2026-W25"
            return orig(dt, name, field, **kw)
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-1", "reference_type": "Weekly Team Update",
                "reference_name": "WTU-2026-W25-EMP-1",
                "description": "", "priority": "Medium", "modified": "",
            })
            self.assertEqual(item["source_key"], "weekly_report")
            self.assertEqual(item["source_label"], "BÁO CÁO TUẦN")
            self.assertEqual(item["action_label"], "Điền báo cáo")
            self.assertTrue(item["action_url"].startswith("/weekly-update?week="))
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    def test_resolve_approval_returns_approval_url(self):
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            # Don't fail on title/name lookup -- return None so resolver uses ref_name.
            return None
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-2", "reference_type": "GBS Purchase Order",
                "reference_name": "GBS-PO-20260612-02710",
                "description": "", "priority": "High", "modified": "",
            })
            self.assertEqual(item["source_key"], "approval")
            self.assertEqual(item["source_label"], "PHÊ DUYỆT")
            self.assertEqual(item["action_label"], "Phê duyệt")
            self.assertEqual(
                item["action_url"],
                "/approval?id=GBS-PO-20260612-02710&type=gbs_purchase_order",
            )
        finally:
            frappe.db.get_value = orig

    def test_resolve_task_routes_to_app_task(self):
        orig = frappe.db.get_value
        def _get(dt, name, field, **kw):
            if dt == "Task" and field == "subject":
                return "Design homepage"
            return None
        frappe.db.get_value = _get
        try:
            item = resolvers.resolve_item({
                "name": "todo-3", "reference_type": "Task",
                "reference_name": "TASK-2026-00084",
                "description": "", "priority": "Medium", "modified": "",
            })
            self.assertEqual(item["source_key"], "task")
            self.assertEqual(item["source_label"], "CÔNG VIỆC")
            self.assertEqual(item["action_label"], "Xem công việc")
            self.assertEqual(item["action_url"], "/app/task/TASK-2026-00084")
            self.assertEqual(item["title"], "Design homepage")
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    def test_unknown_doctype_uses_desk_fallback_with_dashes(self):
        orig = frappe.db.get_value
        frappe.db.get_value = lambda *a, **kw: None
        try:
            item = resolvers.resolve_item({
                "name": "todo-4", "reference_type": "Mystery Doc",
                "reference_name": "MYS-001",
                "description": "x", "priority": "Low", "modified": "",
            })
            self.assertEqual(item["source_key"], "generic")
            self.assertEqual(item["action_url"], "/app/mystery-doc/MYS-001")
            self.assertNotIn("/approval", item["action_url"])
        finally:
            frappe.db.get_value = orig

    def test_no_reference_type_links_to_todo_desk(self):
        item = resolvers.resolve_item({
            "name": "todo-5", "reference_type": "", "reference_name": "",
            "description": "Ad-hoc", "priority": "Medium", "modified": "",
        })
        self.assertEqual(item["source_key"], "generic")
        self.assertEqual(item["action_url"], "/app/todo/todo-5")
        self.assertNotIn("/approval", item["action_url"])
