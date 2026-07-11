# Copyright (c) 2026, eCentric and contributors
"""Upload hardening + package lifecycle rules (orphan prevention foundation).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_upload_rules
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestEsignUploadRules(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        fx.ensure_process()
        fx.ensure_settings(allowed_users=[])
        fx.ensure_profile()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _pkg(self, tag):
        mgr = fx.user(fx.PFX + tag + "m@example.com")
        req = fx.user(fx.PFX + tag + "r@example.com")
        fx.employee(req, reports_to=fx.employee(mgr))
        biz = fx.draft_payment_request(req)
        frappe.set_user(req)
        pkg = pkgsvc.get_or_create_draft("EC Payment Request", biz,
                                         "ZZESN_PAYR")
        frappe.set_user("Administrator")
        return pkg, biz, req, mgr

    def test_upload_requires_existing_draft(self):
        frappe.set_user(fx.user(fx.PFX + "u0@example.com"))
        with self.assertRaises(Exception):
            pkgsvc.get_or_create_draft("EC Payment Request", "EC-PAYR-2099-99999",
                                       "ZZESN_PAYR")
        frappe.set_user("Administrator")

    def test_file_and_row_created_attached_no_orphan(self):
        pkg, biz, req, _ = self._pkg("u1")
        frappe.set_user(req)
        row = pkgsvc.add_file(pkg.name, "a.pdf", fx.PDF, requires_signature=1)
        frappe.set_user("Administrator")
        f = frappe.db.get_value("File", row.file,
                                ["attached_to_doctype", "attached_to_name", "is_private"],
                                as_dict=True)
        self.assertEqual((f.attached_to_doctype, f.attached_to_name, f.is_private),
                         ("EC Payment Request", biz, 1))
        self.assertEqual(len(row.sha256), 64)

    def test_denylist_zero_byte_and_invalid_pdf(self):
        pkg, _, req, _ = self._pkg("u2")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            pkgsvc.add_file(pkg.name, "x.crdownload", fx.PDF)
        with self.assertRaises(Exception):
            pkgsvc.add_file(pkg.name, "x.pdf", b"")
        with self.assertRaises(Exception):  # signable must be real PDF
            pkgsvc.add_file(pkg.name, "x.pdf", b"not a pdf at all", requires_signature=1)
        with self.assertRaises(Exception):  # PDF magic but no EOF (partial upload)
            pkgsvc.add_file(pkg.name, "y.pdf", b"%PDF-1.4 truncated", requires_signature=1)
        frappe.set_user("Administrator")

    def test_flags_are_independent_not_exclusive(self):
        pkg, _, req, _ = self._pkg("u3")
        frappe.set_user(req)
        row = pkgsvc.add_file(pkg.name, "both.pdf", fx.PDF, requires_signature=1,
                              share_with_partner=1)
        frappe.set_user("Administrator")
        got = frappe.db.get_value("EC Digital Signature File", row.name,
                                  ["requires_signature", "share_with_partner",
                                   "is_supporting_document"], as_dict=True)
        self.assertEqual((got.requires_signature, got.share_with_partner,
                          got.is_supporting_document), (1, 1, 0))

    def test_only_requester_and_only_draft_can_mutate(self):
        pkg, biz, req, mgr = self._pkg("u4")
        frappe.set_user(req)
        row = pkgsvc.add_file(pkg.name, "a.pdf", fx.PDF, requires_signature=1)
        pkgsvc.save_placements(pkg.name, [{"signature_file": row.name, "page_index": 1,
                                           "x": 1, "y": 2 + 12 * lvl, "width": 10, "height": 10,
                                           "level_no": lvl, "signature_type": "mock"}
                                          for lvl in (1, 2, 3, 4)])  # profile requires all 4
        frappe.set_user(mgr)  # not the requester
        with self.assertRaises(frappe.PermissionError):
            pkgsvc.add_file(pkg.name, "b.pdf", fx.PDF)
        frappe.set_user(req)
        fx.submit_and_lock(biz, req, pkg.name)   # Draft -> Locked -> Active
        with self.assertRaises(Exception):       # post-lock immutability
            pkgsvc.add_file(pkg.name, "late.pdf", fx.PDF)
        frappe.set_user("Administrator")

    def test_preflight_blocks_missing_placement_and_no_signable(self):
        pkg, _, req, _ = self._pkg("u5")
        frappe.set_user(req)
        self.assertIn("no_signable_file", pkgsvc.preflight_for_lock(pkg.name))
        row = pkgsvc.add_file(pkg.name, "a.pdf", fx.PDF, requires_signature=1)
        errs = pkgsvc.preflight_for_lock(pkg.name)
        self.assertTrue(any(e.startswith("missing_placement") for e in errs))
        frappe.set_user("Administrator")

    def test_revision_supersedes_and_cancels_inflight(self):
        h = fx.full_stack(fx.PFX + "u6r@example.com", fx.PFX + "u6m@example.com")
        from ecentric_workspace.approval_center.esign import service as esvc
        frappe.set_user(h["mgr"])
        r = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        new = pkgsvc.create_revision(h["pkg"])
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package", h["pkg"],
                                             "status"), "Superseded")
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package", new.name,
                                             "package_version"), 2)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request",
                                             r["signature_request"], "status"), "Superseded")
        # copied structure
        self.assertEqual(len(pkgsvc.package_files(new.name)), 2)
        self.assertEqual(len(pkgsvc.package_placements(new.name)), 4)
