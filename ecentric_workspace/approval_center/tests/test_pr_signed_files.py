# Copyright (c) 2026, eCentric and contributors
"""Signed-file lifecycle (S2B-C1, PR#147 hardened): fail-closed terminal-signed gate,
concurrency-safe + idempotent private storage, hash-mismatch deduplicated review, and
no-binary-in-events.

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
DSR = "EC Digital Signature Request"
PDF2 = b"%PDF-1.4 signed v1\n%%EOF"
PDF_ALT = b"%PDF-1.4 signed v2 different\n%%EOF"

_SIGNED = [{"user_id": "U", "signature_id": "S", "status": "signed"}]


class _SignedAdapter(object):
    """Deterministic adapter double. `status` is the provider document status; `signers`
    is the per-signer list poll_status returns. Retrieval must never call the write spies."""

    def __init__(self, pdf=PDF2, status="signed", signers=None):
        self.pdf = pdf
        self.status = status
        self.signers = _SIGNED if signers is None else signers
        self.writes = {"create": 0, "bulk": 0}
        self.get_calls = 0

    def poll_status(self, document_id):
        return NormalizedDocState(document_id, self.status, signers=self.signers,
                                  files=[{"file_id": "F0"}])

    def get_signed_document(self, document_id, file_id=None):
        self.get_calls += 1
        return {"content": self.pdf, "sha256": hashlib.sha256(self.pdf).hexdigest(),
                "size": len(self.pdf)}

    def create_document(self, ctx):
        self.writes["create"] += 1
        return {"document_id": "x", "files": []}

    def approve_and_sign(self, *a, **k):
        self.writes["bulk"] += 1
        return {"bulk_job_transaction_id": "x"}


def _scts_uat_settings():
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "base_url_allowlist": "scts.uat.local", "username": "erp-bot",
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


def _completed_dsr(pkg_name, user_id="U", status="Approval Completed", action="Sign"):
    """Insert a DSR in the given terminal state so the fail-closed gate can evaluate.
    ignore_links skips Link validation for the dummy Approval Engine references."""
    return frappe.get_doc({
        "doctype": DSR, "provider": "SCTS", "environment": "UAT", "package": pkg_name,
        "approval_request": "AR-DUMMY", "request_level": "LVL-DUMMY",
        "approver_row": "ROW-DUMMY", "action": action, "requested_by": "Administrator",
        "approver": "Administrator", "idempotency_key": "idem-%s-%s" % (pkg_name, user_id),
        "effective_scts_user_id": user_id, "status": status,
    }).insert(ignore_permissions=True, ignore_links=True).name


class TestSignedFiles(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    # ---- blocker 1: fail-closed terminal-signed gate ----

    def test_terminal_status_plus_completed_dsr_accepted(self):
        biz, pkg, dsf = _pkg("sf1@example.com")
        _completed_dsr(pkg)
        original_file = frappe.db.get_value(DSF, dsf, "file")
        original_sha = frappe.db.get_value(DSF, dsf, "sha256")
        ad = _SignedAdapter()  # status 'signed' + signer signed
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertTrue(out["ok"])
        row = frappe.db.get_value(DSF, dsf, ["signed_file", "signed_file_sha256", "file"],
                                  as_dict=True)
        self.assertTrue(row.signed_file)
        self.assertEqual(row.signed_file_sha256, hashlib.sha256(PDF2).hexdigest())
        self.assertEqual(row.file, original_file)         # original attachment unchanged
        self.assertEqual(frappe.db.get_value(DSF, dsf, "sha256"), original_sha)
        self.assertTrue(frappe.db.get_value("File", row.signed_file, "is_private"))
        self.assertEqual(frappe.db.get_value(PKG, pkg, "signed_bundle_complete"), 1)
        self.assertEqual(ad.writes, {"create": 0, "bulk": 0})  # no writes during retrieval

    def test_all_expected_signers_signed_fallback_accepted(self):
        # provider status is NOT an explicit terminal token -> signer-based fallback must
        # accept only because EVERY expected signer is present and signed.
        biz, pkg, dsf = _pkg("sf2@example.com")
        _completed_dsr(pkg, user_id="U")
        ad = _SignedAdapter(status="in_progress",
                            signers=[{"user_id": "U", "signature_id": "S", "status": "signed"}])
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertTrue(out["ok"])
        self.assertTrue(frappe.db.get_value(DSF, dsf, "signed_file"))

    def test_one_signed_one_pending_blocked(self):
        biz, pkg, dsf = _pkg("sf3@example.com")
        _completed_dsr(pkg)
        ad = _SignedAdapter(status="signed", signers=[
            {"user_id": "U", "status": "signed"}, {"user_id": "V", "status": "pending"}])
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "not_terminal_signed")
        self.assertIn("non_signed_signer_present", out["detail"])
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_file"))

    def test_one_signed_one_rejected_blocked(self):
        biz, pkg, dsf = _pkg("sf4@example.com")
        _completed_dsr(pkg)
        ad = _SignedAdapter(status="signed", signers=[
            {"user_id": "U", "status": "signed"}, {"user_id": "V", "status": "rejected"}])
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertFalse(out["ok"])
        self.assertIn("non_signed_signer_present", out["detail"])
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_file"))

    def test_terminal_provider_but_no_completed_dsr_blocked(self):
        # provider says signed, but no DSR reached Approval Completed -> fail closed.
        biz, pkg, dsf = _pkg("sf5@example.com")
        ad = _SignedAdapter()  # terminal, signer signed
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertFalse(out["ok"])
        self.assertIn("not_exactly_one_completed_dsr", out["detail"])
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_file"))

    def test_unexpected_signer_identity_blocked(self):
        # fallback path, all signed, but a returned signer is NOT an expected internal signer.
        biz, pkg, dsf = _pkg("sf6@example.com")
        _completed_dsr(pkg, user_id="U")
        ad = _SignedAdapter(status="in_progress", signers=[
            {"user_id": "U", "status": "signed"}, {"user_id": "STRANGER", "status": "signed"}])
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            out = signed_files.retrieve_and_store_for_package(pkg)
        self.assertFalse(out["ok"])
        self.assertEqual(out["detail"], "unexpected_signer_identity")
        self.assertIsNone(frappe.db.get_value(DSF, dsf, "signed_file"))

    # ---- blocker 2: concurrency-safe + idempotent storage ----

    def test_two_workers_create_exactly_one_file(self):
        # sequential simulation of the row-locked commit path: the second pass reloads under
        # the lock, sees the stored SHA, and short-circuits -> exactly one accepted File.
        biz, pkg, dsf = _pkg("sf7@example.com")
        _completed_dsr(pkg)
        ad = _SignedAdapter()
        with patch.object(signed_files, "get_adapter", lambda s: ad):
            signed_files.retrieve_and_store_for_package(pkg)
            first = frappe.db.get_value(DSF, dsf, "signed_file")
            out2 = signed_files.retrieve_and_store_for_package(pkg)
        self.assertTrue(any(r.get("duplicate") for r in out2["files"]))
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), first)
        self.assertEqual(frappe.db.count("File", {"attached_to_name": biz,
                                                  "file_name": "SIGNED-sign.pdf"}), 1)

    def test_force_same_sha_no_duplicate(self):
        biz, pkg, dsf = _pkg("sf8@example.com")
        _completed_dsr(pkg)
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter()):
            signed_files.retrieve_and_store_for_package(pkg)
            first = frappe.db.get_value(DSF, dsf, "signed_file")
            out = signed_files.retrieve_and_store_for_package(pkg, force=True)
        self.assertTrue(any(r.get("duplicate") for r in out["files"]))
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), first)
        self.assertEqual(frappe.db.count("File", {"attached_to_name": biz,
                                                  "file_name": "SIGNED-sign.pdf"}), 1)

    def test_different_sha_preserves_old_file_and_one_candidate(self):
        biz, pkg, dsf = _pkg("sf9@example.com")
        _completed_dsr(pkg)
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF2)):
            signed_files.retrieve_and_store_for_package(pkg)
        accepted = frappe.db.get_value(DSF, dsf, "signed_file")
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF_ALT)):
            out = signed_files.retrieve_and_store_for_package(pkg, force=True)
        self.assertTrue(any(r.get("hash_mismatch") for r in out["files"]))
        # accepted pointer unchanged; complete flag cleared; provider status marked
        self.assertEqual(frappe.db.get_value(DSF, dsf, "signed_file"), accepted)
        self.assertEqual(frappe.db.get_value(PKG, pkg, "signed_bundle_complete"), 0)
        self.assertEqual(frappe.db.get_value(DSF, dsf, "provider_status"), "SignedHashMismatch")
        alt_sha = hashlib.sha256(PDF_ALT).hexdigest()
        review_name = "REVIEW-%s-sign.pdf" % alt_sha[:8]
        self.assertEqual(frappe.db.count("File", {"attached_to_name": biz,
                                                  "file_name": review_name}), 1)
        self.assertTrue(frappe.db.exists("ToDo", {"reference_type": PKG,
                                                  "reference_name": pkg, "status": "Open"}))

    def test_repeated_mismatch_no_repeated_candidate_files(self):
        biz, pkg, dsf = _pkg("sf10@example.com")
        _completed_dsr(pkg)
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF2)):
            signed_files.retrieve_and_store_for_package(pkg)
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter(PDF_ALT)):
            signed_files.retrieve_and_store_for_package(pkg, force=True)
            signed_files.retrieve_and_store_for_package(pkg, force=True)
            signed_files.retrieve_and_store_for_package(pkg, force=True)
        alt_sha = hashlib.sha256(PDF_ALT).hexdigest()
        review_name = "REVIEW-%s-sign.pdf" % alt_sha[:8]
        self.assertEqual(frappe.db.count("File", {"attached_to_name": biz,
                                                  "file_name": review_name}), 1)
        self.assertEqual(frappe.db.count("ToDo", {"reference_type": PKG,
                                                  "reference_name": pkg, "status": "Open"}), 1)

    # ---- audit hygiene ----

    def test_no_binary_in_events(self):
        biz, pkg, dsf = _pkg("sf11@example.com")
        _completed_dsr(pkg)
        with patch.object(signed_files, "get_adapter", lambda s: _SignedAdapter()):
            signed_files.retrieve_and_store_for_package(pkg)
        rows = frappe.get_all("EC Digital Signature Event", filters={"package": pkg},
                              fields=["request_meta", "response_meta", "error_summary"])
        blob = " ".join((r.request_meta or "") + (r.response_meta or "") + (r.error_summary or "")
                        for r in rows)
        self.assertNotIn("%PDF-", blob)
        import base64 as _b64
        self.assertNotIn(_b64.b64encode(PDF2).decode(), blob)
