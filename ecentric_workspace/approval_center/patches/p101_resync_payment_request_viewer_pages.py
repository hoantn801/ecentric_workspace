# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: multi-page PDFs, and a viewer that stays in its card.

Two defects reported 2026-08-28, both in the placement drawer.

The viewer only ever rendered page 1 and drew EVERY placement on it, so a box belonging to
page 2 sat over page 1 - visibly wrong, and draggable by mistake. Signatures on any page but
the first could not be placed at all. There is now a pager, and only the current page's boxes
are drawn.

`.ecd-viewer` was a centring flex container with no scrolling, so a page larger than the
frame spilled out over the surrounding card instead of scrolling. It scrolls now, and the
page is centred with `margin:auto` rather than by flex alignment (which cannot scroll).
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
