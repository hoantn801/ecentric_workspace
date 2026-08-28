# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: the requester panel vanished the moment it mattered.

Pressing "Trinh ky" moves requester_signature_status to Processing. The panel's visibility
test accepted only Pending / Failed / Reconciliation Required, so the panel hid itself
immediately after the click - taking with it the "waiting for the provider" state that had
just been added for exactly this moment. Reported 2026-08-28: "pressed it, three or four
minutes, nothing to see".

The panel now stays while Processing, shows what it is waiting for, hides every button (there
is nothing to press) and refreshes itself.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
