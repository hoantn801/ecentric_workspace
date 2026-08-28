# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the drag-clamp fix actually reaches the browser.

The previous change fixed `_clampBox`: dragging a signature box towards the right margin
pinned its LEFT edge near the page edge and then shrank the width to 20pt, so the box looked
like it jumped left and collapsed. The fix keeps the chosen size and slides the box back
inside the page.

That fix lives in document_signing_section.html, which is INJECTED into a Web Page record by
page_sync - it is not served from disk. Shipping it without a resync patch changes the file
in git while the site keeps serving the markup already stored in the record.

Which is what happened: 2026-08-29, tests green, deploy clean, and the same bug reported
within the hour - the browser was still running the old code. The fix was real; it just
never arrived.

Any change to an injected .html needs its own resync patch. No exceptions.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
