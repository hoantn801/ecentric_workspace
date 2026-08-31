# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the narrowed `isMine` actually reaches browsers.

The fix itself shipped on 31/08: the clone button used to appear for `owner` as well as
`requested_by`, but `command_service.clone_request` only accepts `requested_by` (or a System
Manager). Whoever created the record without being the requester saw the button, clicked it,
and got refused - a button whose only function was disappointment.

The fix landed in main_section.html and went nowhere. That file is not served from disk; it
is injected into a Web Page record, and the record only changes when a patch calls sync().
The last page resync was p108, so the site kept serving the pre-fix markup while the repo,
the tests and the deploy all looked clean.

Found by reading the live page after the deploy instead of trusting that green tests plus a
successful deploy meant the code was running. Third time this class of bug has shipped, so
test_html_change_needs_resync.py now pins a content hash for every template injected into
this page - editing one without adding a resync patch fails the suite.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
