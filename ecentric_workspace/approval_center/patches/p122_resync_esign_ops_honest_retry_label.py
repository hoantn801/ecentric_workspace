# Copyright (c) 2026, eCentric and contributors
"""Re-publish the esign ops page so the retry button says what it will actually do.

The button was labelled "Thử lại" with the explanation "xếp lại chân ký này vào hàng đợi để
gửi lệnh ký một lần nữa". For a leg that had already been sent it did not do that, and could
not: the worker holds a one-way latch that refuses to re-send, because the signing command is
not idempotent and a second send can put a second signature on the same document. The leg was
moved to Manual Review instead. So the button promised a send and delivered a status change,
on the one screen in the system whose whole purpose is to stop that kind of silence.

Worse, the latch had made itself unfalsifiable. `retry_signature_request` incremented
`request_attempt` and THEN queued the job, while the latch counted `request_attempt > 1` as
evidence of a prior send - so by the time the worker looked, the counter was already 2 and
EVERY retry bounced, including one on a leg that had never been sent at all. The action could
never do the thing it was named after.

Two changes behind this resync:
  * `state.may_have_sent` is now the single definition, used by the worker and by this page,
    so the label cannot drift from the behaviour. `request_attempt` is out of it - it counts
    how many times a person asked, not whether anything left the building. `accepted_at`
    already covers the case it was added for (a 200 with no transaction id).
  * The page asks that question per leg and labels accordingly: "Gửi lại" when nothing has
    gone out, "Đối soát lại" when something may have, each with its own explanation in the
    confirm box. `data-act` stays "retry" - only the wording changes.

Separate patch from p120 because p120 has already run on production, and a patch runs ONCE.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
