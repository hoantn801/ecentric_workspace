# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so a send-back cycle explains itself.

resubmit() now revises the signing package (see platform/esign/lifecycle.py), and when
digital signatures had already been collected it restarts the approval from level 1 -
because those signatures attest to a document set that no longer exists. That is a visible
change in behaviour, so the page must say why rather than silently sending everyone back.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
