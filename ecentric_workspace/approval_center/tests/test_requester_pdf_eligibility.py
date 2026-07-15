# Copyright (c) 2026, eCentric and contributors
"""Requester PDF eligibility + package-file surfacing (fix/scts-requester-pdf-eligibility).

Deployed symptom: prepare_requester_signing_package reported 'no eligible private PDF' for
EC-PAYR-2026-00009 even though two valid private-PDF File rows existed (one with
attached_to_field=request_attachment, one with a null field).

Exact root cause (verified in code, NOT a File-eligibility predicate): the File IS fetched
(frappe.get_all ignores permissions) and added to the requester's Draft package. But prepare
built config.files via ui_state.signing_ui_state -> service.get_signing_status, which for a
SUBMITTED Payment Request (an EC Approval Request exists) resolves the package only by
active_package_for_request(ar) [status='Active'] OR {approval_request: ar}. The unlocked
requester Draft has status='Draft' AND no approval_request (set only at lock), so it matched
neither -> package=None -> config.files=[] -> the frontend's empty-files guard showed
'no eligible private PDF'.

Fix: prepare now derives config.files directly from pkgsvc.package_files(pkg.name); and
_add_requester_pdf_files de-dupes multiple File rows for the same physical PDF (by SHA-256 and
canonical file_url, updated in-loop) and identifies PDFs from file_name/file_url (no MIME).

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_pdf_eligibility
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import requester
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
PROFILE = "ZZESN_PAYR"
PDFNAME = "SCTS_UAT_ONLY_VOID_Test_Document_002.pdf"


def _requester_profile():
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _gates_off():
    n = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": "Mock", "environment": "UAT"}, "name")
    frappe.db.set_value("EC Digital Signature Provider Settings", n,
                        {"integration_enabled": 0, "allow_document_creation": 0, "allow_signing": 0})


def _pending_submitted(tag):
    """A submitted Payment Request in requester pre-approval (ar EXISTS, current_level 0) with
    NO package yet - the exact EC-PAYR-2026-00009 shape."""
    _requester_profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    _gates_off()
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _attach(biz, user, file_name=PDFNAME, content=None, is_private=1,
            attached_to_field=None, attached_to_name=None):
    frappe.set_user(user)
    doc = frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": is_private,
                          "attached_to_doctype": BD, "attached_to_name": attached_to_name or biz,
                          "attached_to_field": attached_to_field,
                          "content": content if content is not None else fx.PDF}
                         ).insert(ignore_permissions=True)
    frappe.set_user("Administrator")
    return doc.name


def _signable(pkg):
    return frappe.get_all("EC Digital Signature File",
                          filters={"package": pkg, "requires_signature": 1}, fields=["name"])


def _pkg(biz):
    return pkgsvc.draft_package_for_business(BD, biz)


class TestRequesterPdfEligibility(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def _prepare(self, user, biz):
        frappe.set_user(user)
        try:
            return requester.prepare_requester_signing_package(BD, biz)
        finally:
            frappe.set_user("Administrator")

    def test_request_attachment_pdf_is_eligible_and_surfaced(self):
        # the PRIMARY bug: config.files must surface the Draft package's file for a submitted PR
        req, biz = _pending_submitted("pe1")
        _attach(biz, req, attached_to_field="request_attachment")
        out = self._prepare(req, biz)
        self.assertEqual(out["status"], "Draft")
        self.assertEqual(len(out["config"]["files"]), 1)         # was [] before the fix
        self.assertEqual(len(_signable(_pkg(biz))), 1)

    def test_null_field_direct_attachment_is_eligible_or_deduped(self):
        req, biz = _pending_submitted("pe2")
        _attach(biz, req, file_name=PDFNAME, attached_to_field="request_attachment")
        _attach(biz, req, file_name=PDFNAME, attached_to_field=None)   # same physical PDF, null field
        out = self._prepare(req, biz)
        self.assertEqual(len(out["config"]["files"]), 1)         # twin deduped -> exactly one
        self.assertEqual(len(_signable(_pkg(biz))), 1)

    def test_duplicate_records_same_physical_pdf_one_package_file(self):
        req, biz = _pending_submitted("pe3")
        _attach(biz, req, file_name="a.pdf", content=fx.PDF)
        _attach(biz, req, file_name="b.pdf", content=fx.PDF)     # identical content, different name
        self._prepare(req, biz)
        self.assertEqual(len(_signable(_pkg(biz))), 1)           # SHA dedupe -> one

    def test_repeated_prepare_idempotent(self):
        req, biz = _pending_submitted("pe4")
        _attach(biz, req, attached_to_field="request_attachment")
        self._prepare(req, biz)
        self._prepare(req, biz)
        self.assertEqual(len(_signable(_pkg(biz))), 1)

    def test_wrong_doctype_name_public_nonpdf_rejected(self):
        req, biz = _pending_submitted("pe5")
        _attach(biz, req, file_name="pub.pdf", is_private=0)                 # public -> excluded
        _attach(biz, req, file_name="note.txt")                             # non-PDF -> skipped
        other = fx.draft_payment_request(req)                              # a different PR
        _attach(biz, req, file_name="other.pdf", attached_to_name=other)   # wrong name -> excluded
        out = self._prepare(req, biz)
        self.assertEqual(len(out["config"]["files"]), 0)
        self.assertEqual(len(_signable(_pkg(biz))), 0)

    def test_runtime_business_values_are_canonical(self):
        req, biz = _pending_submitted("pe6")
        _attach(biz, req, attached_to_field="request_attachment")
        self._prepare(req, biz)
        pkg = _pkg(biz)
        row = frappe.db.get_value("EC Digital Signature Package", pkg,
                                  ["business_doctype", "business_name"], as_dict=True)
        self.assertEqual(row.business_doctype, "EC Payment Request")
        self.assertEqual(row.business_name, biz)

    def test_no_provider_or_dsr_with_gates_off(self):
        req, biz = _pending_submitted("pe7")
        _attach(biz, req, attached_to_field="request_attachment")
        before = frappe.db.count("EC Digital Signature Request")
        self._prepare(req, biz)
        self.assertEqual(frappe.db.count("EC Digital Signature Request"), before)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package", _pkg(biz), "status"),
                         "Draft")
