# Copyright (c) 2026, eCentric and contributors
"""Action Center API tests (get_action_items)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.action_center import api as ac_api


TEST_USER_A = "ac_test_user_a@example.test"
TEST_USER_B = "ac_test_user_b@example.test"


def _make_user(email):
    if frappe.db.exists("User", email):
        frappe.db.set_value("User", email, "enabled", 1)
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "AC", "send_welcome_email": 0, "enabled": 1,
    }).insert(ignore_permissions=True)
    return email


def _todo(user, ref_type, ref_name, desc="x"):
    return frappe.get_doc({
        "doctype": "ToDo", "allocated_to": user,
        "reference_type": ref_type, "reference_name": ref_name,
        "status": "Open", "description": desc,
    }).insert(ignore_permissions=True)


class TestActionCenterApi(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = _make_user(TEST_USER_A)
        cls.user_b = _make_user(TEST_USER_B)

    def _cleanup_todos(self, user):
        for t in frappe.get_all("ToDo",
                filters={"allocated_to": user, "description": ["like", "%ac_test%"]},
                pluck="name"):
            frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)

    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup_todos(self.user_a)
        self._cleanup_todos(self.user_b)

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup_todos(self.user_a)
        self._cleanup_todos(self.user_b)

    def test_guest_returns_401(self):
        frappe.set_user("Guest")
        try:
            result = ac_api.get_action_items()
            self.assertFalse(result.get("success"))
            self.assertEqual(result.get("count"), 0)
        finally:
            frappe.set_user("Administrator")

    def test_only_current_user_todos_returned(self):
        _todo(self.user_a, "Brand Approver", "FES-VN-A", desc="ac_test mine A")
        _todo(self.user_b, "Brand Approver", "FES-VN-B", desc="ac_test other B")
        frappe.set_user(self.user_a)
        try:
            result = ac_api.get_action_items()
            self.assertTrue(result["success"])
            for it in result["items"]:
                self.assertEqual(
                    frappe.db.get_value("ToDo", it["todo_name"], "allocated_to"),
                    self.user_a, "Returned a ToDo not owned by user A")
        finally:
            frappe.set_user("Administrator")

    def test_wtu_item_action_url_does_not_contain_approval(self):
        # Tag-test: even if get_value lookup fails, action_url must be
        # /weekly-update-style, not /approval.
        _todo(self.user_a, "Weekly Team Update", "WTU-stub-1",
              desc="ac_test wtu")
        frappe.set_user(self.user_a)
        try:
            result = ac_api.get_action_items()
            matched = [it for it in result["items"]
                       if it["todo_name"] and it.get("reference_type") == "Weekly Team Update"]
            self.assertTrue(matched, "WTU item should be in feed")
            for it in matched:
                self.assertNotIn("/approval", it["action_url"])
                self.assertTrue(it["action_url"].startswith("/weekly-update"))
                self.assertEqual(it["source_label"], "BÁO CÁO TUẦN")
        finally:
            frappe.set_user("Administrator")

    def test_one_bad_row_does_not_break_feed(self):
        # A row whose reference_type is junk should be skipped (or fall back
        # to desk route), not cause the API to fail.
        _todo(self.user_a, "Brand Approver", "VALID-1", desc="ac_test ok")
        _todo(self.user_a, "Definitely Not A DocType ZZZ", "X",
              desc="ac_test broken")
        frappe.set_user(self.user_a)
        try:
            result = ac_api.get_action_items()
            self.assertTrue(result["success"])
            # At least the valid one returned.
            self.assertGreaterEqual(result["count"], 1)
            valid = [it for it in result["items"]
                     if it.get("reference_name") == "VALID-1"]
            self.assertEqual(len(valid), 1)
            self.assertIn("/approval?id=VALID-1", valid[0]["action_url"])
        finally:
            frappe.set_user("Administrator")
