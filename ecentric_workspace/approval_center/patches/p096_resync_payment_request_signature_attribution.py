# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: a signature was drawn on a box nobody had signed.

2026-08-28, EC-PAYR-2026-00029. The provider had exactly ONE signature - the requester's.
The screen showed two: the "Direct Manager Review" box carried a signature as well, and its
signer card read "Da ky", while that level was still waiting for a decision.

Cause: the overlay matched signatures to boxes BY EMAIL. The same person had signed as
requester and also happened to be a candidate for that approval level, so the display
attributed his requester signature to the approver box too.

That is the same "email matching is too loose" defect that was fixed in the VERIFICATION
path on 2026-08-27, reintroduced in the DISPLAY path a night later. A screen that misreports
who signed a payment approval is not a cosmetic problem.

Attribution now comes from our own completed signing legs (requester leg -> requester slot,
approval leg -> its own level), never from a candidate list.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
