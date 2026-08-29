# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so the requester can attach files when sent back.

Two rules met and left the "Chỉnh sửa & gửi lại" screen with NO way to attach anything:

  * document_signing_section.html hides the legacy `request_attachment` field, on the
    principle of "one requester upload surface";
  * that other surface - "+ Tải tài liệu" in TÀI LIỆU & KÝ SỐ - is disabled while the
    signing package is Locked, which is exactly its state after a send-back (the revision
    is only created INSIDE the resubmit call).

So the most common reason for a send-back - "thiếu chứng từ" - was also the one thing the
requester could not act on. The field was in the DOM the whole time, just display:none, which
is why it looked like a backend problem for a full night.

The hide rule now yields on the edit screen only, anchored on `#payr-resubmit` - a button
that exists only in that mode.

This markup lives in a Web Page record, not on disk: without a resync patch the file changes
in git while the site keeps serving the old CSS. Third time this week that this is worth
writing down.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
