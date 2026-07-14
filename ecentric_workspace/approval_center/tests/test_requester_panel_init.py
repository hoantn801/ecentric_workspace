# Copyright (c) 2026, eCentric and contributors
"""Requester panel INITIALIZATION contract (fix/scts-requester-panel-init).

Deployed bug: the panel resolved the Payment Request name only from window state
(window.EC_PPH_PR / window.PaymentRequest.state.id), but the page URL is
/approvals/payment-request?id=EC-PAYR-2026-00009 - so at init neither was set, pr() returned
nothing, and refresh() exited before ever calling readiness, leaving #ec-req-sign hidden.

This suite pins the source-level contract; the full runtime behaviour is executed by the
node:vm harness (no jsdom needed):
  node ecentric_workspace/approval_center/tests/js/test_requester_panel_init.mjs
which asserts: ?id= initializes+shows; ?name / ?payment_request_name / window-state
fallbacks; missing id exits safely (hidden, no readiness call, one dev diagnostic, no throw);
readiness called exactly once per init; repeated init does not duplicate handlers; boolean
visibility (is_requester / pending_requester_signature / requester_signature_required).

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_requester_panel_init
"""
import os

from frappe.tests.utils import FrappeTestCase

_UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esign", "ui")


def _panel():
    with open(os.path.join(_UI, "requester_signing_panel.html"), encoding="utf-8") as fh:
        return fh.read()


class TestRequesterPanelInit(FrappeTestCase):
    def test_resolves_id_first_then_fallbacks(self):
        h = _panel()
        self.assertIn("new URLSearchParams(location.search)", h)
        # governed order: id primary, then name, then payment_request_name, then window state
        self.assertIn('q.get("id") || q.get("name") || q.get("payment_request_name")', h)
        self.assertIn("window.EC_PPH_PR", h)
        self.assertIn("window.PaymentRequest.state.id", h)

    def test_validates_non_empty_and_no_dom_text_inference(self):
        h = _panel()
        self.assertIn('.trim()', h)          # blank/whitespace rejected
        self.assertIn("return id || null;", h)
        # never infers the id from arbitrary DOM text
        for bad in ("innerText", "textContent.match", "querySelector"):
            self.assertNotIn(bad, h)

    def test_missing_id_is_safe_and_hidden_with_one_diagnostic(self):
        h = _panel()
        self.assertIn("developer_mode", h)        # diagnostic gated to dev/debug mode
        self.assertIn("console.debug", h)
        # the no-id branch returns (panel stays display:none) rather than throwing
        self.assertIn("panel stays hidden", h)

    def test_readiness_called_once_and_visibility_boolean_only(self):
        h = _panel()
        self.assertEqual(h.count("esign.api.requester_signing_readiness"), 1)
        self.assertIn('b(c, "is_requester") && b(c, "pending_requester_signature")', h)
        self.assertIn('b(c, "requester_signature_required")', h)
        self.assertNotIn("m.ready", h)           # ready/gates/package never gate visibility

    def test_handlers_bound_once_guard(self):
        h = _panel()
        self.assertIn('root.getAttribute("data-ec-bound") !== "1"', h)
        self.assertIn('root.setAttribute("data-ec-bound", "1")', h)

    def test_call_api_readiness_guarded_and_deferred(self):
        h = _panel()
        # never call bare frappe.call; guard by window.frappe.call availability
        self.assertIn('typeof window.frappe.call === "function"', h)
        self.assertNotIn("\n    frappe.call(", h)          # no unguarded bare call
        self.assertEqual(h.count("window.frappe.call("), 3)  # readiness + prepare + lock
        # bounded, idempotent init poller that clears its timer
        self.assertIn("setInterval(", h)
        self.assertIn("clearInterval(", h)
        self.assertIn("_MAX_TRIES", h)
        # safe failure: dev-mode diagnostic, panel stays hidden, no throw
        self.assertIn("frappe.call unavailable within bounded window", h)

    def test_no_cdn_or_raw_private_url_and_governed_endpoints(self):
        h = _panel()
        for bad in ("cdnjs", "unpkg", "jsdelivr", "googleapis", "/private/files/", "http://"):
            self.assertNotIn(bad, h)
        self.assertIn("esign.api.prepare_requester_signing_package", h)
        self.assertIn("esign.api.requester_lock_signing_package", h)
