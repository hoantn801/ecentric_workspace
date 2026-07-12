# Copyright (c) 2026, eCentric and contributors
"""Signed-file lifecycle (S2B-C1): governed retrieval + private storage, idempotency,
hash-mismatch Manual Review, terminal-signed gate, and no-binary-in-events.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_pr_signed_files
"""
import hashlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import package as pkgsvc, signed_files
from ecentric_workspace.approval_center.esign.providers.base import NormalizedDocState
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
PDF2 = b"%PDF-1.4 signed v1\n%%EOF"
PDF_ALT = b"%PDF-1.4 signed v2 different\n%%EOF"


class _SignedAdapter(object):
    def __init__(self, pdf=PDF2, status="signed"):
        self.pdf = pdf
        self.status = status
        self.writes = {"create": 0, "bulk": 0}

    def poll_status(self, document_id):
        signers = [{"user_id": "U", "signature_id": "S", "status": "signed"}] \
            if self.status == "signed" else [{"user_id": "U", "status": "pending"}]
        return NormalizedDocState(document_id, self.status, signers=signers,
                                  files=[{"file_id": "F0"}])

    def get_signed_document(self, document_id, file_id=None):
        return {"content": self.pdf, "sha256": hashlib.sha256(self.pdf).hexdigest(),
                "size": len(self.pdf)}

    # spies: retrieval must never call these
    def create_document(self, ctx):
        self.writes["create"] += 1
        return {"document_id": "x", "files": []}

    def approve_and_sign(self, *a, **k):
        self.writes["bulk"] += 1
        return {"bulk_job_transaction_id": "x"}


def _scts_uat_settings():
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "username": "erp-bot",
            "integration_enabled": 1, "allow_document_creation": 1, "allow_signing": 1}
    if name:
        d = frappe.get_doc("EC Digital Signature Provider Settings", name)
        d.update(vals)
        d.save(ignore_permissions=True)
    else:
        frappe.get_doc(dict({"doctype": "EC Digital Signature Provider Settings",
                             "provider": "SCTS", "environment": "UAT"}, **vals)
                       ).insert(ignore_permissions=True)


def _pkg(reqmail):
    fx.ensure_process()
    fx.ensure_settings(allowed_users=[fx.FIN])
    fx.ensure_profile()
    _scts_uat_settings()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR", "provider", "SCTS")
    req = fx.user(fx.PFX + reqmail)
    biz = fx.draft_payment_request(req)
    frappe.set_user(req)
    profile = frappe.db.get_value("EC Digital Signature Profile", "ZZESN_PAYR", "name")
    pkg = pkgsvc.get_or_create_draft("EC Payment Request", biz, profile)
    dsf = pkgsvc.add_file(pkg.name, "sign.pdf", fx.PDF, requires_signature=1)
    frappe.set_user("Administrator")
    frappe.db.set_value(PKG, pkg.name, "scts_document_id", "SCTS-DOC-1")
    frappe.db.set_value(DSF, dsf.name, "scts_document_file_id", "F0")
    return biz, pkg.name, dsf.name


class TestSignedFiles(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_retrieves_stores_private_and_original_unchanged(self):
        biz, pkg, dsf = _pkg("sf1@example.com")
        original_file = frappe.db.get_value(DSF, dsf, "file")
        original_sha = frappe.db.get_value(DSF, dsf, "sha256")
        ad = _SignedAdapter()
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertTrue(out["ok"])
        row = frappe.db.get_value(DSF, dsf, ["signed_file", "signed_file_sha256", "file"],
                                  as_dict=True)
        self.assertTrue(row.signed_file)
        self.assertEqual(row.signed_file_sha256, hashlib.sha256(PDF2).hexdigest())
        self.assertEqual(row.file, original_file)  # original attachment unchanged
        self.assertEqual(frappe.db.get_value(DSF, dsf, "sha256"), original_sha)
        self.assertTrue(frappe.db.get_value("File", row.signed_file, "is_private"))
        self.assertEqual(frappe.db.get_value(PKG, pkg, "signed_bundle_complete"), 1)
        self.assertEqual(ad.writes, {"create": 0, "bulk": 0})  # no writes during retrieval

    def test_terminal_signed_required(self):
        biz, pkg, dsf = _pkg("sf2@example.com")
        ad = _SignedAdapter(status="pending")
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "document_not_terminal_signed")
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_file"))

    def test_idempotent_no_duplicate_file(self):
        biz, pkg, dsf = _pkg("sf3@example.com")
        ad = _SignedAdapter()
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            signed_files.retrieve_and_store_for_package(pkg)
            first = frappe.db.get_value(DSF, dsf, "signed_file")
            out2 = signed_files.retrieve_and_store_for_package(pkg)
        self.assertTrue(any(r.get("duplicate") for r in out2["files"]))
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), first)  # same File
        self.assertEqual(frappe.db.count("File", {"attached_to_name": biz,
                                                  "file_name": "SIGNED-sign.pdf"}), 1)

    def test_different_hash_enters_manual_review(self):
        biz, pkg, dsf = _pkg("sf4@example.com")
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF2)):
            signed_files.retrieve_and_store_for_package(pkg)
        # a forced re-verify that returns DIFFERENT bytes -> hash mismatch + review
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF_ALT)):
            out = signed_files.retrieve_and_store_for_package(pkg, force=True)
        self.assertTrue(any(r.get("hash_mismatch") for r in out["files"]))
        self.assertEqual(frappe.db.get_value(PKG, pkg, "signed_bundle_complete"), 0)
        self.assertEqual(frappe.db.get_value(DSF, dsf, "provider_status"), "SignedHashMismatch")
        self.assertTrue(frappe.db.exists("ToDo", {"reference_type": PKG,
                                                  "reference_name": pkg, "status": "Open"}))

    def test_no_binary_in_events(self):
        biz, pkg, dsf = _pkg("sf5@example.com")
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter()):
            signed_files.retrieve_and_store_for_package(pkg)
        rows = frappe.get_all("EC Digital Signature Event", filters={"package": pkg},
                              fields=["request_meta", "response_meta", "error_summary"])
        blob = " ".join((r.request_meta or "") + (r.response_meta or "") + (r.error_summary or "")
                        for r in rows)
        self.assertNotIn("%PDF-", blob)
        import base64 as _b64
        self.assertNotIn(_b64.b64encode(PDF2).decode(), blob)
