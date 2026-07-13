# Copyright (c) 2026, eCentric and contributors
"""Signed-file hash-mismatch review resolution (Phase 5). Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signed_file_review
"""
import hashlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import review, signed_files
from ecentric_workspace.approval_center.tests import test_pr_signed_files as base

PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"


def _mismatched(reqmail):
    """A package whose signable file has an accepted signed file AND a pending review
    candidate (different SHA), via the governed retrieval path."""
    biz, pkg, dsf = base._pkg(reqmail)
    base._completed_dsr(pkg)
    with patch.object(signed_files, "get_adapter", lambda s: base._SignedAdapter(base.PDF2)):
        signed_files.retrieve_and_store_for_package(pkg)
    with patch.object(signed_files, "get_adapter", lambda s: base._SignedAdapter(base.PDF_ALT)):
        signed_files.retrieve_and_store_for_package(pkg, force=True)
    return biz, pkg, dsf


class TestSignedFileReview(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_candidate_recorded_on_mismatch(self):
        biz, pkg, dsf = _mismatched("rv1@example.com")
        row = frappe.db.get_value(DSF, dsf, ["provider_status", "signed_review_candidate",
                                             "signed_review_sha256"], as_dict=True)
        self.assertEqual(row.provider_status, "SignedHashMismatch")
        self.assertTrue(row.signed_review_candidate)
        self.assertEqual(row.signed_review_sha256, hashlib.sha256(base.PDF_ALT).hexdigest())

    def test_accept_promotes_candidate_preserves_both(self):
        biz, pkg, dsf = _mismatched("rv2@example.com")
        prior = frappe.db.get_value(DSF, dsf, "signed_file")
        cand = frappe.db.get_value(DSF, dsf, "signed_review_candidate")
        out = review.accept_candidate(dsf, reason="reviewed ok")
        self.assertTrue(out["resolved"])
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), cand)  # promoted
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file_sha256"),
                         hashlib.sha256(base.PDF_ALT).hexdigest())
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_review_candidate"))
        self.assertEqual(frappe.db.get_value(DSF, dsf, "provider_status"), "Signed")
        # BOTH file records preserved
        self.assertTrue(frappe.db.exists("File", prior))
        self.assertTrue(frappe.db.exists("File", cand))
        self.assertEqual(frappe.db.get_value(PKG, pkg, "signed_bundle_complete"), 1)

    def test_reject_keeps_accepted_file(self):
        biz, pkg, dsf = _mismatched("rv3@example.com")
        prior = frappe.db.get_value(DSF, dsf, "signed_file")
        cand = frappe.db.get_value(DSF, dsf, "signed_review_candidate")
        out = review.reject_candidate(dsf, reason="fake")
        self.assertTrue(out["resolved"])
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), prior)  # unchanged
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_review_candidate"))
        self.assertEqual(frappe.db.get_value(DSF, dsf, "provider_status"), "Signed")
        self.assertTrue(frappe.db.exists("File", cand))  # candidate File preserved

    def test_keep_existing(self):
        biz, pkg, dsf = _mismatched("rv4@example.com")
        prior = frappe.db.get_value(DSF, dsf, "signed_file")
        out = review.keep_existing(dsf)
        self.assertTrue(out["resolved"])
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), prior)
        self.assertEqual(frappe.db.get_value(DSF, dsf, "provider_status"), "Signed")

    def test_idempotent_no_pending(self):
        biz, pkg, dsf = _mismatched("rv5@example.com")
        review.accept_candidate(dsf)
        out2 = review.accept_candidate(dsf)  # nothing left to resolve
        self.assertFalse(out2["resolved"])
        self.assertEqual(out2["reason"], "no_pending_review")

    def test_requires_system_manager(self):
        biz, pkg, dsf = _mismatched("rv6@example.com")
        req = frappe.db.get_value("EC Payment Request", biz, "requested_by")
        frappe.set_user(req)
        with self.assertRaises(frappe.PermissionError):
            review.accept_candidate(dsf)
        frappe.set_user("Administrator")

    def test_original_attachment_never_touched(self):
        biz, pkg, dsf = _mismatched("rv7@example.com")
        original = frappe.db.get_value(DSF, dsf, "file")
        original_sha = frappe.db.get_value(DSF, dsf, "sha256")
        review.accept_candidate(dsf)
        self.assertEqual(frappe.db.get_value(DSF, dsf, "file"), original)
        self.assertEqual(frappe.db.get_value(DSF, dsf, "sha256"), original_sha)


    def test_only_signed_file_review_todo_closed(self):
        # a mismatch creates the marked review ToDo; add UNRELATED open ToDos on the same
        # package; resolving must close ONLY the signed-file-review ToDo.
        biz, pkg, dsf = _mismatched("rv8@example.com")
        other1 = frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                                 "reference_type": PKG, "reference_name": pkg,
                                 "description": "reconciliation follow-up",
                                 "assigned_by": "Administrator"}).insert(ignore_permissions=True)
        other2 = frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                                 "reference_type": PKG, "reference_name": pkg,
                                 "description": "manual review of approval",
                                 "assigned_by": "Administrator"}).insert(ignore_permissions=True)
        review.accept_candidate(dsf)
        self.assertEqual(frappe.db.get_value("ToDo", other1.name, "status"), "Open")
        self.assertEqual(frappe.db.get_value("ToDo", other2.name, "status"), "Open")
        from ecentric_workspace.approval_center.esign.signed_files import REVIEW_TODO_MARKER
        marked = frappe.get_all("ToDo", filters={
            "reference_type": PKG, "reference_name": pkg,
            "description": ["like", "%" + REVIEW_TODO_MARKER + "%"]},
            fields=["status"])
        self.assertTrue(marked and all(m.status == "Closed" for m in marked))
