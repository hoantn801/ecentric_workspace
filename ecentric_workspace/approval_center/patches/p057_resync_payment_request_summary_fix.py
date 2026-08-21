# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Payment Request Web Page: header summary now shows the real covered/total signer
count (was hardcoded '0/N'). Idempotent; drift lock self-maintains via record_live_sha."""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
