# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the bigger signature block reaches the browser.

The signature stamp sat as a small mark on the left of a large empty box, with the
"Ky boi / scts.com.vn / date / time" block pushed far to the right: the image was pinned at
42% of the width and the text at a fixed 8px, both spread apart by `space-between`. The
bigger the box, the smaller and lonelier the signature looked.

Now the image and the text are centred as one group, the image takes the full box height at
its true aspect ratio, and the text is sized from the BOX HEIGHT by _fitSig().

document_signing_section.html is INJECTED into a Web Page record by page_sync - it is not
served from disk. Shipping it without a resync patch changes the file in git while the site
keeps serving the markup already stored in the record. That is exactly how the drag-clamp
fix was reported broken within the hour of a clean deploy (see p102).

Any change to an injected .html needs its own resync patch. No exceptions.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
