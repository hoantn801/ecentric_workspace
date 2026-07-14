# Copyright (c) 2026, eCentric and contributors
"""Requester signing panel VISIBILITY + state/action mapping
(fix/scts-requester-panel-visibility).

Deployed root cause of the "panel visually hidden" bug: requester_signing_readiness returns
`checks` as BARE BOOLEANS, but the panel read `checks[k].ok` (object shape) - always
undefined - so `visible` was always false and the panel never appeared even though
is_requester / pending_requester_signature / requester_signature_required were all true.
A secondary gap: readiness only inspected the "Active" package, so a requester's LOCAL
Draft -> Locked package lifecycle (which never reaches "Active" while the write gates are OFF)
was invisible, leaving the four UI states / Lock action unreachable.

Two layers are pinned here:
  * Backend readiness (DB / FrappeTestCase; run in PR CI / bench): the additive
    package_present / placements_ready / package_locked keys map the four local states while
    the gates are OFF, the visibility inputs stay true while overall `ready` is false, and the
    pre-existing keys + `ready`/`reasons` are unchanged (regression guard).
  * Panel + editor CONTRACT (static string checks on the shipped HTML; also runnable without
    a DB): visibility decoupled from `ready`/gates, bare booleans read (no `.ok`), the four
    status strings + four-state button mapping, closed gates info-only, governed endpoints
    only, no CDN/raw URL, no actor/level selector, manual coordinate controls hidden by
    default, and the approver editor drag/save preserved.

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_panel_visibility
The true DOM runtime cases (button clicks; PDF drag/drop -> normalized placement) need jsdom
+ pdf.js and are exercised in PR CI / UAT.
"""
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import requester
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
AR = "EC Approval Request"
PROFILE = "ZZESN_PAYR"

_UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esign", "ui")


def _panel_html():
    with open(os.path.join(_UI, "requester_signing_panel.html"), encoding="utf-8") as fh:
        return fh.read()


def _editor_html():
    with open(os.path.join(_UI, "pdf_placement_editor.html"), encoding="utf-8") as fh:
        return fh.read()


def _requester_profile():
    fx.ensure_process()
    fx.ensure_settings(allowed_users=None)
    fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _gates(integration=1, doc=1, signing=1):
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "Mock", "environment": "UAT"}, "name")
    frappe.db.set_value("EC Digital Signature Provider Settings", name,
                        {"integration_enabled": integration,
                         "allow_document_creation": doc, "allow_signing": signing})


def _submit_deferred(biz, req):
    """Bare submit - Option B defers Level 1 for a requester-signing profile (no lock)."""
    frappe.set_user(req)
    papi.submit_request(biz)
    frappe.set_user("Administrator")


# --------------------------------------------------------------------------- #
# 1) Backend readiness - four-state mapping (DB; PR CI / bench)
# --------------------------------------------------------------------------- #
class TestRequesterReadinessStateMapping(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def _no_pkg(self, tag):
        _requester_profile()
        h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
        # a SECOND request by the same requester, submitted deferred with NO package yet
        # (mirrors the deployed EC-PAYR-2026-00009 evidence).
        _gates(0, 0, 0)
        biz = fx.draft_payment_request(h["requester"])
        _submit_deferred(biz, h["requester"])
        return h["requester"], biz

    def _rd(self, req, biz):
        frappe.set_user(req)
        try:
            return requester.requester_signing_readiness(BD, biz)
        finally:
            frappe.set_user("Administrator")

    def test_visibility_inputs_true_while_not_ready(self):
        req, biz = self._no_pkg("pv1")
        rd = self._rd(req, biz)
        c = rd["checks"]
        self.assertTrue(c["is_requester"])
        self.assertTrue(c["pending_requester_signature"])
        self.assertTrue(c["requester_signature_required"])
        # panel MUST be visible (inputs true) while overall readiness is false for
        # package/gate reasons - the exact deployed condition.
        self.assertFalse(rd["ready"])
        for r in ("gates_enabled", "package_active_hash_valid", "placements_complete"):
            self.assertIn(r, rd["reasons"])

    def test_initial_state_no_package(self):
        req, biz = self._no_pkg("pv2")
        c = self._rd(req, biz)["checks"]
        self.assertFalse(c["package_present"])   # -> "Chua chuan bi goi" + Prepare
        self.assertFalse(c["placements_ready"])
        self.assertFalse(c["package_locked"])

    def test_present_but_incomplete_state(self):
        req, biz = self._no_pkg("pv3")
        frappe.set_user(req)
        pkg = pkgsvc.get_or_create_draft(BD, biz, PROFILE, allow_submitted=True)
        pkgsvc.add_file(pkg.name, "sign_0.pdf", fx.PDF, requires_signature=1)  # no placement
        frappe.set_user("Administrator")
        c = self._rd(req, biz)["checks"]
        self.assertTrue(c["package_present"])    # -> "Thieu vi tri ky" + Set placement
        self.assertFalse(c["placements_ready"])
        self.assertFalse(c["package_locked"])

    def test_ready_to_lock_then_locked(self):
        _requester_profile()
        h = fx.full_stack(fx.PFX + "pv4@example.com", fx.PFX + "pv4m@example.com")
        _gates(0, 0, 0)
        biz = fx.draft_payment_request(h["requester"])
        # complete Draft package (all levels placed) BEFORE submit, then submit deferred.
        pkg = fx.build_package(biz, h["requester"], levels=(1, 2, 3, 4))
        _submit_deferred(biz, h["requester"])
        c1 = self._rd(h["requester"], biz)["checks"]
        self.assertTrue(c1["package_present"])
        self.assertTrue(c1["placements_ready"])   # -> "San sang khoa" + Lock
        self.assertFalse(c1["package_locked"])
        frappe.set_user(h["requester"])
        requester.requester_lock_signing_package(BD, biz)
        frappe.set_user("Administrator")
        c2 = self._rd(h["requester"], biz)["checks"]
        self.assertTrue(c2["package_locked"])      # -> "Goi da khoa", no action
        self.assertFalse(c2["placements_ready"])

    def test_gate_toggle_keeps_visibility_inputs(self):
        req, biz = self._no_pkg("pv5")
        c_off = self._rd(req, biz)["checks"]
        _gates(1, 1, 1)
        c_on = self._rd(req, biz)["checks"]
        for k in ("is_requester", "pending_requester_signature", "requester_signature_required"):
            self.assertEqual(c_off[k], c_on[k])
        self.assertNotEqual(c_off["gates_enabled"], c_on["gates_enabled"])

    def test_additive_keys_do_not_perturb_ready_path(self):
        _requester_profile(); _gates(1, 1, 1)
        h = fx.full_stack(fx.PFX + "pv6@example.com", fx.PFX + "pv6m@example.com")
        rd = self._rd(h["requester"], h["biz"])
        for k in ("package_present", "placements_ready", "package_locked"):
            self.assertNotIn(k, rd["reasons"])   # new keys never feed `ready`/`reasons`


# --------------------------------------------------------------------------- #
# 2) Panel + editor CONTRACT (static string checks)
# --------------------------------------------------------------------------- #
class TestRequesterPanelContract(FrappeTestCase):
    def test_visibility_decoupled_from_ready_and_gates(self):
        h = _panel_html()
        self.assertIn('b(c, "is_requester") && b(c, "pending_requester_signature")', h)
        self.assertIn('b(c, "requester_signature_required")', h)
        self.assertNotIn("m.ready", h)          # visibility never couples to overall readiness
        self.assertIn("elGate.style.display", h)  # gate check only toggles the info banner

    def test_reads_bare_booleans_not_dot_ok(self):
        h = _panel_html()
        self.assertIn("function b(c, k) { return !!(c && c[k]); }", h)
        self.assertNotIn(".ok)", h)

    def test_four_status_strings_present(self):
        h = _panel_html()
        for s in ("Chưa chuẩn bị gói", "Thiếu vị trí ký",
                  "Sẵn sàng khoá", "Gói đã khoá"):
            self.assertIn(s, h)

    def test_state_to_button_mapping(self):
        h = _panel_html()
        for s in ("Chuẩn bị gói ký", "Đặt vị trí chữ ký",
                  "Khoá gói ký"):
            self.assertIn(s, h)
        self.assertIn('prepShow = false; lockShow = false;', h)  # locked hides BOTH actions

    def test_gates_shown_as_information_only(self):
        h = _panel_html()
        self.assertIn('id="ecReqGate"', h)
        self.assertIn('class="ec-info"', h)

    def test_only_governed_endpoints_and_no_cdn(self):
        h = _panel_html()
        self.assertIn("esign.api.requester_signing_readiness", h)
        self.assertIn("esign.api.prepare_requester_signing_package", h)
        self.assertIn("esign.api.requester_lock_signing_package", h)
        for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis", "/private/files/", "http://"):
            self.assertNotIn(bad, h)

    def test_panel_has_no_approval_level_or_actor_selector(self):
        h = _panel_html()
        for bad in ("level_no", "approver_row", "request_level", "<select"):
            self.assertNotIn(bad, h)

    def test_manual_coordinate_controls_hidden_by_default(self):
        e = _editor_html()
        self.assertIn("<details", e)
        self.assertIn('id="ecpphNumRows"', e)
        self.assertLess(e.index("<details"), e.index('id="ecpphNumRows"'))
        self.assertNotIn("<details open", e)

    def test_approver_editor_drag_and_save_preserved(self):
        e = _editor_html()
        self.assertIn("mousedown", e)
        self.assertIn("esign.api.save_placements", e)
        self.assertIn('id="ecpphAdd"', e)
