# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Payment Request Web Page: SCTS-standard default box size + 'Ky thu' signature
preview in the placement drawer. Idempotent; the drift lock self-maintains via record_live_sha."""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
