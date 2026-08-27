# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page after four signing-UX fixes.

1. The drawer stopped depending on CSS it does not own. It asked for the ERP shell's
   variables twenty times; the shell lives in head_html on production, so one redefinition
   up there changed the drawer's chrome underneath it - which is what "the buttons suddenly
   went ugly" was. It now declares its own palette. In the same pass, every rule scoped to
   `.ec-docsign` gained a `.ecd-drawer-ov` twin, because the overlay is moved to <body> and
   would otherwise leave all 23 of those rules behind.

2. "Ky thu" now draws what SCTS actually prints: the signature image on the left and the
   "Ky boi / scts.com.vn / date / time" block on the right. It used to draw the image alone,
   so the preview and the real thing did not match - which is the one job a preview has.

3. Signatures that have really been applied are pulled back from the provider and drawn in
   their own boxes, and each signer card says who signed and when instead of showing a bare
   tick. Toggling "Ky thu" no longer wipes them: the old cleanup removed every .sigprev and
   the real signatures carry that class too.

4. After "Duyet & Ky" the current step says it is waiting for the provider and the page
   refreshes itself every ten seconds, with a deadline. Previously nothing on screen changed
   for a minute or two, which is indistinguishable from a button that did nothing.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
