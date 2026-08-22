# Copyright (c) 2026, eCentric and contributors
"""Phase A2 (shell-reconciled): the unified section is injected without regressing the Shared
ERP Shell v1 contracts on the Payment Request page, and the approver block is wrapped hidden.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_document_section_shell
"""
import os
from frappe.tests.utils import FrappeTestCase
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


class TestDocumentSectionShell(FrappeTestCase):
    def _h(self):
        return page_sync._html()

    def test_shell_anchors_preserved(self):
        h = self._h()
        self.assertEqual(h.count('data-ec-shell="1"'), 1)          # shell mount, exactly once
        self.assertEqual(h.count('class="ec-shell-mount"'), 1)
        self.assertIn("ec-shell-tbright", h)                       # header-right slot
        self.assertIn("data-ec-shell-header-right", h)             # notification bell slot
        self.assertIn("ec-shell-crumblink", h)                     # clickable Approval Center breadcrumb
        self.assertIn("/approvals", h)
        self.assertIn("ec-shell-fallback", h)                      # fallback navigation

    def test_section_injected_requester_raw_replaced(self):
        h = self._h()
        self.assertEqual(h.count('id="ec-docsign"'), 1)
        self.assertNotIn('id="ec-req-sign"', h)                    # requester raw panel replaced
        self.assertNotIn('id="ec-pph-editor"', h)                  # inline editor replaced
        self.assertEqual(h, self._h())                             # idempotent

    def test_approver_block_wrapped_default_hidden(self):
        h = self._h()
        self.assertIn('id="ec-approver-wrap" style="display:none"', h)
        self.assertIn('id="ec-esign-panel"', h)                    # approver panel preserved inside wrapper

    def test_no_duplicate_shell_or_business_chrome(self):
        h = self._h()
        self.assertEqual(h.count('data-ec-shell="1"'), 1)
        self.assertEqual(h.count('id="payr-body"'), 1)             # single business-content region
        self.assertEqual(h.count('class="ec-shell-mount"'), 1)

    def test_section_mounts_into_business_content(self):
        h = self._h()
        self.assertIn("#ec-payr-root .ec-main .content", h)
        self.assertIn('getElementById("payr-body")', h)

    def test_governed_endpoints_only_no_cdn(self):
        h = self._h()
        self.assertIn("platform.esign.api.", h)
        for m in ("document_setup_state", "set_document_requires_signature", "signer_plan",
                  "set_representative_attachment", "signing_readiness", "placement_state",
                  "save_placement", "delete_placement"):
            self.assertIn('"' + m + '"', h)
        self.assertIn("/api/method/upload_file", h)
        for bad in ("cdnjs", "unpkg", "jsdelivr", "http://", "localStorage"):
            self.assertNotIn(bad, h)

    def test_shell_main_source_preserved(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(page_sync.__file__)))
        main = open(os.path.join(base, "payment_request", "ui", "main_section.html"),
                    encoding="utf-8").read()
        # A2 did not touch the shell main: anchors present exactly as shipped
        self.assertEqual(main.count('data-ec-shell="1"'), 1)
        self.assertEqual(main.count('class="ec-shell-mount"'), 1)
        self.assertIn("ec-shell-tbright", main)

    # ---- smoothness overnight pass (2026-08-21) regressions ----
    def test_no_legacy_placement_editor_injected(self):
        h = self._h()
        self.assertNotIn("pdf_placement_editor", h)
        self.assertNotIn('id="ec-pph-coords"', h)
        self.assertNotIn('id="ec-pph-editor"', h)              # standalone legacy editor never injected

    def test_drawer_isolates_legacy_layers(self):
        h = self._h()
        self.assertIn("#ec-pph-editor{display:none", h)        # legacy requester editor always hidden
        self.assertIn("html.ecd-drawer-open", h)               # drawer-open hides legacy layers

    def test_local_first_drawer_markers(self):
        h = self._h()
        self.assertIn("hydrateBoxes", h)                       # full redraw ONLY on open/reload
        self.assertIn("_onDragMove", h); self.assertIn("_onDragEnd", h)
        self.assertIn("requestAnimationFrame", h)              # rAF-coalesced drag
        self.assertIn("ecdPlaceHint", h)                       # visible PDF helper hint
        self.assertIn("Đang chọn vị trí", h)                   # active placement-button state

    def test_serialized_save_and_caches(self):
        h = self._h()
        self.assertIn("_dispatch", h)                          # per-box serialized save (no double-create)
        self.assertIn("pend.inflight", h)
        self.assertIn("pend.queued", h)
        self.assertIn("pdfDocs", h)                            # PDF cached per file_url across reopens
        self.assertIn("rowsStale", h)                          # rows refreshed once on close, not per save

    def test_identity_watcher_present(self):
        h = self._h()
        self.assertIn("_checkIdentity", h)
        self.assertIn("_loadTok", h)
        self.assertIn("_clearDocState", h)

    def test_progressive_submit_cta(self):
        h = self._h()
        self.assertIn("Tiếp tục: Thêm chứng từ", h)
        self.assertIn('id="payr-continue"', h)
        self.assertIn("continueToDocuments", h)
        self.assertNotIn('id="payr-submit"', h)                # submit CTA removed from the create stage

    def test_title_field_present(self):                       # 2026-08-23: explicit title input
        h = self._h()
        self.assertIn('data-model="request_title"', h)
        self.assertIn("Tiêu đề yêu cầu", h)
