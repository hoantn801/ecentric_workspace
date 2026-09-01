# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so it stops swallowing the server's own message.

Found 02/09 while running the E2E by hand. Submitting a request with no attachment gave

    "Đã có lỗi. Vui lòng thử lại."

while the server had returned exactly the sentence the person needed:

    "Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."

The page had a branch for precisely this case - `applyBackendError` tests for "tệp đính kèm" -
but it read the message from `e.message`, and Frappe does not put a `frappe.throw` message
there. It goes in `_server_messages` (a nested JSON string), sometimes `responseJSON.message`,
sometimes `exception`. `e.message` was always empty, so every business error fell through to
the catch-all sentence and the branch that was supposed to point at the document section never
ran once.

`extractServerMsg` is lifted from ai_topup, which has read those fields correctly all along,
and `mapErr` / `friendlyErr` / `applyBackendError` now all use it. Six other feature pages
still read `e.message` only - listed in BACKLOG_ESIGN.md, not touched here.

Separate patch from p118/p119 because both have already run on production, and a patch runs
ONCE.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
