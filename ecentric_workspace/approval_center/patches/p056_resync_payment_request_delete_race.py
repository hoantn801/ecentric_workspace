# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Payment Request Web Page after the delete-race hardening (serialized per-box
delete + backend no-resurrect guard). Also the first sync that records the post-processed live
sha (shared.page_sync.record_live_sha), ending the manual sha-chasing on this page. Idempotent."""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
