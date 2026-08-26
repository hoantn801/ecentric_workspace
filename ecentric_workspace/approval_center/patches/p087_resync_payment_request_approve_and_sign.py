# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: approval levels that require a digital signature
now show a "Duyệt & Ký" button.

Pilot UAT VOID 5 (2026-08-27): the backend correctly refused a plain approve with "Cấp duyệt
này yêu cầu ký số. Vui lòng dùng chức năng 'Duyệt & Ký'." - but the page only rendered
Duyệt / Yêu cầu bổ sung / Từ chối, so the approver was told to use a control that did not
exist. Signing an approval level was only possible by calling the API by hand.

Web Pages are served from the database, so the code change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
