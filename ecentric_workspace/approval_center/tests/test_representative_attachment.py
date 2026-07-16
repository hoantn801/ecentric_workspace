# Copyright (c) 2026, eCentric and contributors
"""Phase A2: request_attachment backward-compatible representative pointer.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_representative_attachment
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import document_setup as ds
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD = "EC Payment Request"


def _profile():
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _pending(tag):
    _profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _attach(biz, user, name="a.pdf"):
    frappe.set_user(user)
    d = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1,
                        "attached_to_doctype": BD, "attached_to_name": biz, "content": fx.PDF}
                       ).insert(ignore_permissions=True)
    frappe.set_user("Administrator")
    return d.file_url


class TestRepresentativeAttachment(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_empty_pointer_set_on_first_upload(self):
        req, biz = _pending("r1")
        frappe.db.set_value(BD, biz, "request_attachment", None)
        url = _attach(biz, req, "one.pdf")
        frappe.set_user(req)
        out = ds.set_representative_attachment(BD, biz, url)
        frappe.set_user("Administrator")
        self.assertTrue(out["ok"]); self.assertTrue(out["changed"])
        self.assertEqual(frappe.db.get_value(BD, biz, "request_attachment"), url)

    def test_additional_upload_preserves_pointer(self):
        req, biz = _pending("r2")
        u1 = _attach(biz, req, "one.pdf"); u2 = _attach(biz, req, "two.pdf")
        frappe.db.set_value(BD, biz, "request_attachment", None)
        frappe.set_user(req)
        ds.set_representative_attachment(BD, biz, u1)
        out2 = ds.set_representative_attachment(BD, biz, u2)          # second upload
        frappe.set_user("Administrator")
        self.assertFalse(out2["changed"])                            # not overwritten
        self.assertEqual(frappe.db.get_value(BD, biz, "request_attachment"), u1)

    def test_existing_pointer_preserved(self):
        req, biz = _pending("r3")
        frappe.db.set_value(BD, biz, "request_attachment", "/private/files/original.pdf")
        u = _attach(biz, req, "new.pdf")
        frappe.set_user(req)
        out = ds.set_representative_attachment(BD, biz, u)
        frappe.set_user("Administrator")
        self.assertFalse(out["changed"])
        self.assertEqual(frappe.db.get_value(BD, biz, "request_attachment"),
                         "/private/files/original.pdf")

    def test_file_not_attached_rejected(self):
        req, biz = _pending("r4")
        frappe.db.set_value(BD, biz, "request_attachment", None)
        frappe.set_user(req)
        out = ds.set_representative_attachment(BD, biz, "/private/files/foreign.pdf")
        frappe.set_user("Administrator")
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "not_attached")
        self.assertFalse(frappe.db.get_value(BD, biz, "request_attachment"))

    def test_requester_only_no_sm_bypass(self):
        req, biz = _pending("r5")
        frappe.db.set_value(BD, biz, "request_attachment", None)
        url = _attach(biz, req, "one.pdf")
        sm = fx.user(fx.PFX + "r5sm@example.com", roles=("Employee", "System Manager"))
        frappe.set_user(sm)
        with self.assertRaises(frappe.PermissionError):
            ds.set_representative_attachment(BD, biz, url)
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):                # Administrator != requester
            ds.set_representative_attachment(BD, biz, url)

    def test_all_files_visible_via_a1_after_pointer(self):
        req, biz = _pending("r6")
        frappe.db.set_value(BD, biz, "request_attachment", None)
        u1 = _attach(biz, req, "one.pdf"); _attach(biz, req, "two.pdf")
        frappe.set_user(req)
        ds.set_representative_attachment(BD, biz, u1)
        st = ds.get_document_setup_state(BD, biz)
        frappe.set_user("Administrator")
        # both physical documents still surfaced by A1 (pointer is not the list source)
        self.assertGreaterEqual(st["summary"]["documents"], 2)
