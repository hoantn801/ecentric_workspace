# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: one place to handle documents, and a way to undo.

Two things reported on the first run of the send-back flow:

  * the "TÀI LIỆU & KÝ SỐ" block renders on the detail page AND inside the edit form, so one
    screen showed two upload buttons. The block still renders in both places - approvers open
    it to look at signatures - but uploading and removing now happen only inside
    "Chỉnh sửa & gửi lại". main_section flags the mode on <html>; the block reads the flag
    rather than inspecting a page structure it must not depend on.

  * attaching the wrong file had no undo. Without one, the requester adds the right file too
    and leaves both, and the approver guesses which is which.

Removal is deliberately narrow: supporting documents only, only while the request sits at
"Cần bổ sung", only the requester, and never a file that belongs to any signing package of
this request - including a superseded one, because such a file has been signed. It writes a
line into the request history: no silent change to a payment record.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
