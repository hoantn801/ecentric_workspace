# Copyright (c) 2026, eCentric and contributors
"""Requester package file ingestion (fix/scts-requester-add-pdf-doctype).

Deployed bug: prepare_requester_signing_package -> _add_requester_pdf_files queried an
UNDEFINED name `DSF`:
    frappe.get_all(DSF, filters={"package": pkg_name}, fields=["sha256"])
-> HTTP 500 NameError: name 'DSF' is not defined. requester.py defined DSR/AR/PKG but not the
package-file DocType constant, so no package was ever created ("Goi: Chua co").

Canonical fix: the package-file DocType is `EC Digital Signature File` (Link `package`, Data
`sha256`), used across package.py / signed_files.py / pilot.py / review.py, each of which
defines `DSF = "EC Digital Signature File"`. requester.py now defines the same constant. NOT
renamed to DSR (EC Digital Signature Request is a different DocType).

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_add_pdf_files
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import requester
from ecentric_workspace.approval_center.esign import hashing
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
PROFILE = "ZZESN_PAYR"


def _requester_profile():
    fx.ensure_process()
    fx.ensure_settings(allowed_users=None)
    fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _gates_off():
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "Mock", "environment": "UAT"}, "name")
    frappe.db.set_value("EC Digital Signature Provider Settings", name,
                        {"integration_enabled": 0, "allow_document_creation": 0, "allow_signing": 0})


def _pending_no_pkg(tag):
    _requester_profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    _gates_off()
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _attach_private_pdf(biz, requester_user, file_name="req_evidence.pdf", content=None):
    frappe.set_user(requester_user)
    doc = frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": 1,
                          "attached_to_doctype": BD, "attached_to_name": biz,
                          "content": content if content is not None else fx.PDF}
                         ).insert(ignore_permissions=True)
    frappe.set_user("Administrator")
    return doc.name


def _signable_rows(pkg_name):
    return frappe.get_all("EC Digital Signature File",
                          filters={"package": pkg_name, "requires_signature": 1},
                          fields=["name", "sha256"])


def _pkg_of(biz):
    return pkgsvc.draft_package_for_business(BD, biz)


class TestRequesterAddPdfFiles(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    # --- import-safety + schema verification (the exact NameError guard) ---
    def test_dsf_constant_defined_and_import_safe(self):
        self.assertEqual(requester.DSF, "EC Digital Signature File")
        self.assertNotEqual(requester.DSF, requester.DSR)   # not the Request DocType

    def test_package_file_doctype_schema(self):
        meta = frappe.get_meta("EC Digital Signature File")
        fields = {df.fieldname: df.fieldtype for df in meta.fields}
        self.assertEqual(fields.get("package"), "Link")     # query filter
        self.assertEqual(fields.get("sha256"), "Data")      # query field
        self.assertIn("requires_signature", fields)

    # --- behaviour ---
    def test_prepare_adds_one_pdf_no_nameerror(self):
        req, biz = _pending_no_pkg("ap1")
        self._sha = _attach_private_pdf(biz, req)
        frappe.set_user(req)
        out = requester.prepare_requester_signing_package(BD, biz)   # must NOT raise NameError
        frappe.set_user("Administrator")
        pkg = _pkg_of(biz)
        self.assertTrue(pkg)
        rows = _signable_rows(pkg)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].sha256)
        self.assertEqual(out.get("status"), "Draft")

    def test_repeated_prepare_does_not_duplicate(self):
        req, biz = _pending_no_pkg("ap2")
        _attach_private_pdf(biz, req)
        frappe.set_user(req)
        requester.prepare_requester_signing_package(BD, biz)
        requester.prepare_requester_signing_package(BD, biz)   # idempotent reuse
        frappe.set_user("Administrator")
        pkgs = frappe.get_all("EC Digital Signature Package",
                              filters={"business_doctype": BD, "business_name": biz})
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(len(_signable_rows(pkgs[0].name)), 1)

    def test_existing_matching_sha_is_reused(self):
        req, biz = _pending_no_pkg("ap3")
        _attach_private_pdf(biz, req, file_name="a.pdf", content=fx.PDF)
        frappe.set_user(req)
        requester.prepare_requester_signing_package(BD, biz)
        frappe.set_user("Administrator")
        # a SECOND private PDF with identical content (same SHA) attached before re-prepare
        _attach_private_pdf(biz, req, file_name="b.pdf", content=fx.PDF)
        frappe.set_user(req)
        requester.prepare_requester_signing_package(BD, biz)
        frappe.set_user("Administrator")
        rows = _signable_rows(_pkg_of(biz))
        self.assertEqual(len(rows), 1)            # same SHA -> not re-added

    def test_no_eligible_pdf_is_safe(self):
        req, biz = _pending_no_pkg("ap4")          # no PDF attached
        frappe.set_user(req)
        out = requester.prepare_requester_signing_package(BD, biz)   # must not raise
        frappe.set_user("Administrator")
        pkg = _pkg_of(biz)
        self.assertTrue(pkg)                       # package still created (Draft)
        self.assertEqual(len(_signable_rows(pkg)), 0)
        self.assertEqual(out.get("status"), "Draft")

    def test_no_provider_or_dsr_records_with_gates_off(self):
        req, biz = _pending_no_pkg("ap5")
        _attach_private_pdf(biz, req)
        before = frappe.db.count("EC Digital Signature Request")
        frappe.set_user(req)
        requester.prepare_requester_signing_package(BD, biz)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("EC Digital Signature Request"), before)  # no DSR
        pkg = _pkg_of(biz)
        status = frappe.db.get_value("EC Digital Signature Package", pkg, "status")
        self.assertEqual(status, "Draft")          # no provider/Active promotion
