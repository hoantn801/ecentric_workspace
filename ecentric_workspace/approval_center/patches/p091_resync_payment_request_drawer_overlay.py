# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the signing drawer overlay covers the viewport.

Reported 2026-08-27 with a screenshot: the sidebar and the page content behind the drawer
were NOT dimmed, even though the overlay is rgba(0,0,0,.35) with inset:0. Page controls
("Yeu cau bo sung" at the top, the status line at the bottom) showed through above and
below the drawer.

Cause: some ancestor sets transform / filter / contain / overflow. Any one of those makes
that ancestor the containing block for position:fixed - or clips what overflows it - so
inset:0 stops meaning "the viewport" and z-index 9999 gets trapped inside the ancestor's
stacking context. The ERP shell CSS lives in head_html on production and is not in this
repo, so it cannot be corrected from here - and should not be: the drawer must not depend
on CSS it does not own. The overlay is therefore moved to be a direct child of <body> when
the drawer opens, which is immune to every ancestor, present and future.

Same change also clears stray signature previews left anywhere on the document layer. An
orphaned preview looks exactly like a real signature placed in the wrong spot.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
