# Copyright (c) 2026, eCentric and contributors
"""Requester package preparation entry point (fix/scts-requester-package-entrypoint). Runs on
the bench: bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_package_entrypoint
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import requester, package as pkgsvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

AR = "EC Approval Request"
PKG = "EC Digital Signature Package"
DSR = "EC Digital Signature Request"
DSF = "EC Digital Signature File"
SETTINGS = "EC Digital Signature Provider Settings"
BD = "EC Payment Request"


def _profile_and_gates_off():
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"provider": "Mock", "approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})
    nm = frappe.db.get_value(SETTINGS, {"provider": "Mock", "environment": "UAT"}, "name")
    if nm:
        frappe.db.set_value(SETTINGS, nm, {"integration_enabled": 1,
                                           "allow_document_creation": 0, "allow_signing": 0})


def _pending_requester(tag):
    _profile_and_gates_off()
    h = fx.full_stack(fx.PFX + tag + "r@x.com", fx.PFX + tag + "m@x.com")
    frappe.db.set_value(AR, h["ar"], {"requester_signature_status": "Pending", "current_level": 0})
    fx.ensure_mapping(h["requester"])
    return h


class TestRequesterPackageEntrypoint(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_pending_requester_can_prepare(self):
        h = _pending_requester("pe1")
        frappe.set_user(h["requester"])
        out = requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(out["package"])
        self.assertIn("config", out)

    def test_other_user_and_admin_denied(self):
        h = _pending_requester("pe2")
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            requester.prepare_requester_signing_package(BD, h["biz"])

    def test_repeated_prepare_reuses_one_package(self):
        h = _pending_requester("pe3")
        frappe.set_user(h["requester"])
        a = requester.prepare_requester_signing_package(BD, h["biz"])
        b = requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(a["package"], b["package"])
        self.assertEqual(frappe.db.count(PKG, {"business_name": h["biz"]}), 1)

    def test_prepare_works_with_write_gates_off(self):
        h = _pending_requester("pe4")   # doc_creation + signing OFF
        frappe.set_user(h["requester"])
        out = requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(frappe.db.exists(PKG, out["package"]))

    def test_no_dsr_or_provider_document_created(self):
        h = _pending_requester("pe5")
        before = frappe.db.count(DSR)
        frappe.set_user(h["requester"])
        out = requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count(DSR), before)  # no fake approval level / DSR
        self.assertIsNone(frappe.db.get_value(PKG, out["package"], "scts_document_id"))

    def test_private_pdfs_included(self):
        h = _pending_requester("pe6")
        # attach a private PDF to the PR
        frappe.get_doc({"doctype": "File", "file_name": "req.pdf", "is_private": 1,
                        "attached_to_doctype": BD, "attached_to_name": h["biz"],
                        "content": b"%PDF-1.4 requester\n%%EOF"}).insert(ignore_permissions=True)
        frappe.set_user(h["requester"])
        out = requester.prepare_requester_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        names = frappe.get_all(DSF, filters={"package": out["package"]}, pluck="file_name")
        self.assertIn("req.pdf", names)

    def test_lock_makes_readiness_hash_true(self):
        h = _pending_requester("pe7")
        frappe.get_doc({"doctype": "File", "file_name": "req2.pdf", "is_private": 1,
                        "attached_to_doctype": BD, "attached_to_name": h["biz"],
                        "content": b"%PDF-1.4 r2\n%%EOF"}).insert(ignore_permissions=True)
        frappe.set_user(h["requester"])
        out = requester.prepare_requester_signing_package(BD, h["biz"])
        pkg = out["package"]
        # place a signature box so preflight passes, then lock
        dsf = frappe.get_all(DSF, filters={"package": pkg, "requires_signature": 1}, pluck="name")[0]
        pkgsvc.save_placements(pkg, [{"signature_file": dsf, "page_index": 1, "x": 50, "y": 50,
                                      "width": 120, "height": 40, "level_no": 1,
                                      "signature_type": "mock"}])
        locked = requester.requester_lock_signing_package(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(locked["locked"])
        self.assertEqual(frappe.db.get_value(PKG, pkg, "status"), "Locked")
        self.assertTrue(frappe.db.get_value(PKG, pkg, "package_hash"))

    def test_existing_approval_level_flow_unchanged(self):
        # a non-requester submit still cannot create a new draft package post-submit
        fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
        frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                            {"requester_signature_required": 0})
        h = fx.full_stack(fx.PFX + "pe8r@x.com", fx.PFX + "pe8m@x.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.get_or_create_draft(BD, h["biz"], "ZZESN_PAYR")  # allow_submitted defaults False
