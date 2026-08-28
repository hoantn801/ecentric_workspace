# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: the action buttons stayed put while the signature flew.

Pressing "Duyet & Ky" sends the signing command and then nothing visible happens for a while -
the provider signs asynchronously. The progress bar already showed a waiting state, but the
"Hanh dong" card kept rendering the same buttons, which reads as "nothing happened, press it
again". Pressing again is a second signature.

Reported 2026-08-28: "bam duyet va ky roi nhung no van con nut nay, va phai 1 luc sau co 2-5
phut no moi bao da xu ly. Delay nhu nay kha khong tot cho UI UX."

Two changes, one in the page and one behind it:
- while waiting, the action card shows only what is happening and no buttons at all, and it
  re-checks every 5 seconds instead of 10;
- the backend no longer waits for the one-minute cron to notice the signature: after the
  provider accepts, a short bounded read-only loop asks again a few times over the first
  eighty seconds. It can never re-send a signing command - that is gated on status "Queued".
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
