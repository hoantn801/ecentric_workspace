# Copyright (c) 2026, eCentric and contributors
"""Governed Signing Inbox scope + pagination (Phase 3). Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signing_inbox
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import inbox
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestSigningInbox(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_active_approver_sees_own_item(self):
        h = fx.full_stack(fx.PFX + "ib1r@example.com", fx.PFX + "ib1m@example.com")
        frappe.set_user(h["mgr"])
        out = inbox.signing_inbox()
        frappe.set_user("Administrator")
        names = [r["business_name"] for r in out["rows"]]
        self.assertIn(h["biz"], names)
        row = [r for r in out["rows"] if r["business_name"] == h["biz"]][0]
        self.assertTrue(row["is_active_approver"])
        self.assertEqual(row["active_level"], 1)

    def test_requester_is_not_in_inbox(self):
        h = fx.full_stack(fx.PFX + "ib2r@example.com", fx.PFX + "ib2m@example.com")
        frappe.set_user(h["requester"])
        out = inbox.signing_inbox()
        frappe.set_user("Administrator")
        self.assertNotIn(h["biz"], [r["business_name"] for r in out["rows"]])

    def test_non_approver_does_not_leak(self):
        h = fx.full_stack(fx.PFX + "ib3r@example.com", fx.PFX + "ib3m@example.com")
        other = fx.user(fx.PFX + "ib3x@example.com")
        frappe.set_user(other)
        out = inbox.signing_inbox()
        frappe.set_user("Administrator")
        self.assertNotIn(h["biz"], [r["business_name"] for r in out["rows"]])

    def test_scope_query_and_counts_use_same_scope(self):
        h = fx.full_stack(fx.PFX + "ib4r@example.com", fx.PFX + "ib4m@example.com")
        frappe.set_user(h["mgr"])
        out = inbox.signing_inbox(filters={"bucket": "my_pending"})
        frappe.set_user("Administrator")
        self.assertEqual(out["counts"]["my_pending"], out["total"])

    def test_pagination_is_server_side(self):
        h = fx.full_stack(fx.PFX + "ib5r@example.com", fx.PFX + "ib5m@example.com")
        frappe.set_user(h["mgr"])
        out = inbox.signing_inbox(start=0, page_length=1)
        frappe.set_user("Administrator")
        self.assertEqual(out["page_length"], 1)
        self.assertLessEqual(len(out["rows"]), 1)

    def test_system_manager_sees_all_in_scope(self):
        h = fx.full_stack(fx.PFX + "ib6r@example.com", fx.PFX + "ib6m@example.com")
        frappe.get_doc("User", h["mgr"]).add_roles("System Manager")
        frappe.set_user(h["mgr"])
        out = inbox.signing_inbox()
        frappe.set_user("Administrator")
        self.assertTrue(out["is_system_manager"])

    def test_no_raw_bytes_in_rows(self):
        h = fx.full_stack(fx.PFX + "ib7r@example.com", fx.PFX + "ib7m@example.com")
        frappe.set_user(h["mgr"])
        out = inbox.signing_inbox()
        frappe.set_user("Administrator")
        blob = frappe.as_json(out)
        self.assertNotIn("%PDF-", blob)
