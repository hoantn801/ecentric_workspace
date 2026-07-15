# Copyright (c) 2026, eCentric and contributors
"""Requester package STABILIZATION (fix/scts-requester-stabilization).

Consolidates: (1) state-machine invariants - zero-placement packages are never lockable and
'Locked + 0 placements + ready' is impossible; (2) governed recovery of an invalid locked
package; (3) PDF.js asset served as .js (not .mjs octet-stream) + editor bootstrap contract;
(4) fresh-request lifecycle (pre-submission note; post-submission panel); shared resolver
surfaces the requester Draft.

DB tests run on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_stabilization
The static contract tests also hold without a DB.
"""
import hashlib
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import requester
from ecentric_workspace.approval_center.esign import service as svc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
PROFILE = "ZZESN_PAYR"
_UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esign", "ui")
_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "..", "public", "vendor", "pdfjs")


def _editor():
    return open(os.path.join(_UI, "pdf_placement_editor.html"), encoding="utf-8").read()


def _panel():
    return open(os.path.join(_UI, "requester_signing_panel.html"), encoding="utf-8").read()


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


def _pending(tag):
    _requester_profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    _gates_off()
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _draft_with_file(req, biz):
    frappe.set_user(req)
    pkg = pkgsvc.get_or_create_draft(BD, biz, PROFILE, allow_submitted=True)
    pkgsvc.add_file(pkg.name, "sign.pdf", fx.PDF, requires_signature=1)
    frappe.set_user("Administrator")
    return pkg.name


def _place(req, biz, pkg):
    f = [r for r in pkgsvc.package_files(pkg) if r.requires_signature][0]
    frappe.set_user(req)
    pkgsvc.save_placements(pkg, [{"signature_file": f.name, "page_index": 1, "x": 50, "y": 80,
                                  "width": 120, "height": 40, "level_no": 1,
                                  "signature_type": "mock"}])
    frappe.set_user("Administrator")


# --------------------------------------------------------------------------- #
# 1) State machine (DB)
# --------------------------------------------------------------------------- #
class TestRequesterStateMachine(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_zero_placement_never_lockable(self):
        req, biz = _pending("sm1")
        _draft_with_file(req, biz)            # file but NO placement
        frappe.set_user(req)
        with self.assertRaises(frappe.ValidationError):
            requester.requester_lock_signing_package(BD, biz)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package",
                                             pkgsvc.draft_package_for_business(BD, biz), "status"),
                         "Draft")

    def test_placement_then_lockable(self):
        req, biz = _pending("sm2")
        pkg = _draft_with_file(req, biz)
        _place(req, biz, pkg)
        frappe.set_user(req)
        rd = requester.requester_signing_readiness(BD, biz)["checks"]
        self.assertTrue(rd["placements_ready"])
        self.assertFalse(rd["package_locked"])
        requester.requester_lock_signing_package(BD, biz)
        rd2 = requester.requester_signing_readiness(BD, biz)["checks"]
        frappe.set_user("Administrator")
        self.assertTrue(rd2["package_locked"])
        self.assertFalse(rd2["package_invalid"])
        self.assertFalse(rd2["placements_ready"])

    def test_locked_zero_placement_is_invalid_never_ready(self):
        req, biz = _pending("sm3")
        pkg = _draft_with_file(req, biz)
        _place(req, biz, pkg)
        frappe.set_user(req); requester.requester_lock_signing_package(BD, biz)
        frappe.set_user("Administrator")
        # remove the placement -> Locked + 0 placements (the 00009 shape)
        for pl in frappe.get_all("EC Digital Signature Placement", filters={"package": pkg}, pluck="name"):
            frappe.delete_doc("EC Digital Signature Placement", pl, ignore_permissions=True, force=True)
        frappe.set_user(req)
        rd = requester.requester_signing_readiness(BD, biz)["checks"]
        frappe.set_user("Administrator")
        self.assertTrue(rd["package_invalid"])
        self.assertFalse(rd["package_locked"])
        self.assertFalse(rd["placements_ready"])


# --------------------------------------------------------------------------- #
# 2) Recovery (DB)
# --------------------------------------------------------------------------- #
class TestRequesterRecovery(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def _make_invalid(self, tag):
        req, biz = _pending(tag)
        pkg = _draft_with_file(req, biz)
        _place(req, biz, pkg)
        frappe.set_user(req); requester.requester_lock_signing_package(BD, biz)
        frappe.set_user("Administrator")
        for pl in frappe.get_all("EC Digital Signature Placement", filters={"package": pkg}, pluck="name"):
            frappe.delete_doc("EC Digital Signature Placement", pl, ignore_permissions=True, force=True)
        return req, biz, pkg

    def test_recovery_cancels_invalid_then_fresh_draft(self):
        req, biz, pkg = self._make_invalid("rc1")
        frappe.set_user(req)
        out = requester.requester_reset_invalid_package(BD, biz)
        self.assertEqual(out["status"], "Cancelled")
        # a fresh prepare now builds a NEW draft (the cancelled one is terminal)
        requester.prepare_requester_signing_package(BD, biz)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package", pkg, "status"), "Cancelled")
        self.assertTrue(pkgsvc.draft_package_for_business(BD, biz))

    def test_recovery_refuses_valid_package(self):
        req, biz = _pending("rc2")
        pkg = _draft_with_file(req, biz)
        _place(req, biz, pkg)
        frappe.set_user(req)
        requester.requester_lock_signing_package(BD, biz)      # valid Locked
        with self.assertRaises(frappe.ValidationError):
            requester.requester_reset_invalid_package(BD, biz)  # refused
        frappe.set_user("Administrator")

    def test_recovery_requester_only(self):
        req, biz, pkg = self._make_invalid("rc3")
        other = fx.user(fx.PFX + "rc3other@example.com")
        frappe.set_user(other)
        with self.assertRaises(frappe.PermissionError):
            requester.requester_reset_invalid_package(BD, biz)
        frappe.set_user("Administrator")

    def test_recovery_makes_no_provider_or_dsr(self):
        req, biz, pkg = self._make_invalid("rc4")
        before = frappe.db.count("EC Digital Signature Request")
        frappe.set_user(req); requester.requester_reset_invalid_package(BD, biz)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("EC Digital Signature Request"), before)


# --------------------------------------------------------------------------- #
# 3) Fresh request + resolver (DB)
# --------------------------------------------------------------------------- #
class TestFreshRequestLifecycle(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_pre_submission_note_for_owner(self):
        _requester_profile()
        h = fx.full_stack(fx.PFX + "fr1@example.com", fx.PFX + "fr1m@example.com")
        frappe.set_user(h["requester"])
        biz = fx.draft_payment_request(h["requester"])       # NOT submitted
        frappe.db.set_value(BD, biz, "approval_type", AT)    # so requester policy resolves
        rd = requester.requester_signing_readiness(BD, biz)
        frappe.set_user("Administrator")
        c = rd["checks"]
        self.assertTrue(c["not_submitted"])
        self.assertTrue(c["is_owner"])
        self.assertTrue(c["requester_signature_required"])

    def test_after_submit_panel_inputs_true(self):
        req, biz = _pending("fr2")
        frappe.set_user(req)
        c = requester.requester_signing_readiness(BD, biz)["checks"]
        frappe.set_user("Administrator")
        self.assertTrue(c["is_requester"] and c["pending_requester_signature"]
                        and c["requester_signature_required"])

    def test_get_signing_status_resolves_requester_draft(self):
        req, biz = _pending("fr3")
        pkg = _draft_with_file(req, biz)
        st = svc.get_signing_status(BD, biz)                 # ar exists, pkg is Draft
        self.assertTrue(st.get("package"))
        self.assertEqual(st["package"]["name"], pkg)
        self.assertEqual(len(st["package"]["files"]), 1)


# --------------------------------------------------------------------------- #
# 4) Editor / asset / panel CONTRACT (static; also runs without a DB)
# --------------------------------------------------------------------------- #
class TestEditorAndAssetContract(FrappeTestCase):
    def test_editor_imports_js_not_mjs(self):
        e = _editor()
        self.assertIn('import(PDFJS_BASE + "pdf.js")', e)
        self.assertIn('workerSrc = PDFJS_BASE + "pdf.worker.js"', e)
        self.assertNotIn(".mjs", e)                          # no octet-stream module dependency

    def test_vendored_assets_are_js_and_match_manifest(self):
        man = open(os.path.join(_VENDOR, "PINNED.sha256"), encoding="utf-8").read()
        self.assertIn("  pdf.js", man)
        self.assertIn("  pdf.worker.js", man)
        for name in ("pdf.js", "pdf.worker.js"):
            fp = os.path.join(_VENDOR, name)
            self.assertTrue(os.path.exists(fp), "missing vendored %s" % name)
        self.assertFalse(os.path.exists(os.path.join(_VENDOR, "pdf.mjs")))

    def test_editor_bootstrap_states_and_mount_hook(self):
        e = _editor()
        self.assertIn("window.ecMountPlacementEditor", e)          # inline mount (no reload)
        self.assertIn("Không tải được trình xem PDF", e)           # explicit failure message
        self.assertIn('root.style.display = hasFiles ? "" : "none"', e)  # hide empty toolbar
        self.assertIn("#ec-payr-root .content", e)                 # mounts into content column

    def test_panel_no_reload_inline_mount_and_recovery(self):
        p = _panel()
        self.assertNotIn("location.reload", p)                     # no auto-refresh away
        self.assertIn("window.ecMountPlacementEditor(out.config)", p)
        self.assertIn("requester_reset_invalid_package", p)        # recovery action
        self.assertIn("package_invalid", p)
        self.assertIn("not_submitted", p)                          # pre-submission note
        self.assertIn("#ec-payr-root .content", p)                 # mounts into content column
