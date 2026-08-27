# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: the "Dat vi tri ky" buttons had no click handler.

Regression from the overlay fix in p091. Moving #ecdDrawerOv to <body> - so position:fixed
measures against the viewport - also moved it out of #ec-docsign. The card handlers were
bound with root.querySelectorAll("[data-add]") where root IS #ec-docsign, so the lookup
returned nothing and not one button got a handler. The drawer opened, looked correct, and
did nothing.

The same move broke 23 CSS rules and that was caught and fixed before shipping; the JS
lookups were missed. A test now asserts that nothing inside the overlay is ever looked up
from root.

Web Pages are served from the database, so the source change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
