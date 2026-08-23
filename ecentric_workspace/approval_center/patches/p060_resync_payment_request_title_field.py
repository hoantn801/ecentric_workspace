# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Payment Request Web Page: explicit 'Tieu de yeu cau' field at the top of the
payment form (blank -> auto-generated title as before). Idempotent."""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
