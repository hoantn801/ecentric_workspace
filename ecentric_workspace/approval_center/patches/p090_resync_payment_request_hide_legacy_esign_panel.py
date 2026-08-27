# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the legacy SCTS signing panel stops rendering.

Reported 2026-08-27 during the UAT VOID 6 run: while reviewing a real request, approvers
were shown a raw developer surface titled "Tep ky so (SCTS)" - a numeric coordinate entry
form, a list of placements with their x/y/width/height, and a delete link next to each one.

That panel is the predecessor of the unified drawer. The drawer
(platform/esign/ui/document_signing_section.html) now owns placement, and the real
"Duyet & Ky" button lives in the page's own action panel, where it carries a confirmation
step and a comment box. Nothing in the legacy panel is still needed, so it now renders
nothing. Its module surface (boot / addPlacement / save) is untouched.

The same reasoning already retired #ec-pph-editor permanently; this panel had only been
hidden WHILE the drawer was open, so closing the drawer brought it back - which is exactly
what happened on screen.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
