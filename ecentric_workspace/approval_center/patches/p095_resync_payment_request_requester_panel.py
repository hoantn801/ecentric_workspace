# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the requester can actually sign.

Two holes, either one enough on its own to dead-end the flow:

1. `_esign_requester_panel()` - which owns "Chuan bi goi ky" and "Khoa goi ky" - was defined
   in page_sync and never called. A comment said the unified section had replaced it. The
   unified section contains no such controls, so nothing had replaced anything.

2. `requester_submit_and_sign` had no caller in any screen. The endpoint has worked since
   2026-08-23; there was simply never a "Trinh ky" button.

Between them the requester signing stage was unreachable through the UI from the day it was
built. It looked finished because every test drove the endpoints directly, and both live
runs (27 and 28 August) were completed by calling the API by hand - so the cause survived
two rounds of "there is no button".

Also removes the dead `_esign_editor_panel()` builder: the drawer really did replace the old
placement editor, and dead code that looks live is what let the requester panel stay
forgotten behind a comment.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
