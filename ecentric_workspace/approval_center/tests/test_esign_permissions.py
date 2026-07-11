# Copyright (c) 2026, eCentric and contributors
"""Permission matrices: allowlist fail-closed, mapping requirement, non-approver 403,
requester visibility without approver actions, SM-only ops.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_permissions
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import service as esvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestEsignPermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_empty_allowlist_means_nobody(self):
        h = fx.full_stack(fx.PFX + "p1r@example.com", fx.PFX + "p1m@example.com",
                          allowed=[])
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")

    def test_non_pending_approver_rejected(self):
        h = fx.full_stack(fx.PFX + "p2r@example.com", fx.PFX + "p2m@example.com")
        outsider = fx.user(fx.PFX + "p2o@example.com")
        fx.ensure_settings(allowed_users=h["approvers"] + [outsider])
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            esvc.approve_and_sign("EC Payment Request", h["biz"])
        # CEO is an approver but NOT at the current level (L1)
        frappe.set_user(fx.CEO)
        with self.assertRaises(frappe.PermissionError):
            esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")

    def test_missing_or_unverified_mapping_blocks(self):
        h = fx.full_stack(fx.PFX + "p3r@example.com", fx.PFX + "p3m@example.com")
        m = frappe.db.get_value("EC SCTS User Mapping",
                                {"frappe_user": h["mgr"], "environment": "UAT"}, "name")
        frappe.db.set_value("EC SCTS User Mapping", m, "mapping_status", "Suspended")
        frappe.set_user(h["mgr"])
        with self.assertRaises(Exception):
            esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")

    def test_requester_sees_status_but_cannot_sign_or_ops(self):
        h = fx.full_stack(fx.PFX + "p4r@example.com", fx.PFX + "p4m@example.com")
        frappe.set_user(h["requester"])
        out = esvc.get_signing_status("EC Payment Request", h["biz"])
        self.assertTrue(out["enabled"])  # visible
        with self.assertRaises(frappe.PermissionError):
            esvc.approve_and_sign("EC Payment Request", h["biz"])  # not an approver
        with self.assertRaises(frappe.PermissionError):
            esvc.cancel_signature_request("EC-DSR-2026-00001", "x")  # not SM
        frappe.set_user("Administrator")

    def test_unrelated_user_cannot_read_status(self):
        h = fx.full_stack(fx.PFX + "p5r@example.com", fx.PFX + "p5m@example.com")
        stranger = fx.user(fx.PFX + "p5s@example.com")
        frappe.set_user(stranger)
        with self.assertRaises(frappe.PermissionError):
            esvc.get_signing_status("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")

    def test_docperm_is_sm_only_on_all_esign_doctypes(self):
        for dt in ("EC Digital Signature Provider Settings", "EC SCTS User Mapping",
                   "EC Digital Signature Profile", "EC Digital Signature Package",
                   "EC Digital Signature File", "EC Digital Signature Placement",
                   "EC Digital Signature Request", "EC Digital Signature Event"):
            perms = frappe.get_meta(dt).permissions
            self.assertEqual([p.role for p in perms], ["System Manager"], dt)
