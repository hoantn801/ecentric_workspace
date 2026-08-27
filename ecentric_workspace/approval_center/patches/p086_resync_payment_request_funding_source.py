# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page after the funding-source UI change.

The form now asks for a source TYPE (ĐNMH / PO sổ EC) and then the document, autofills payee
and the REMAINING amount, and shows total/paid/remaining under the amount. Web Pages are
served from the database, so a code change alone does not reach users - the page must be
re-synced. Idempotent (page_sync compares content and skips when unchanged).
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
