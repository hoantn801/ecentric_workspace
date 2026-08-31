# Copyright (c) 2026, eCentric and contributors
"""Re-publish the ops page with the "stop retrying" control for dead signed-PDF retrievals.

The retrieval cron retries forever. When the provider document no longer exists - HTTP 404 -
the thousandth attempt is exactly as useless as the first, but the job still calls SCTS every
30 minutes. On 31/08 two packages had been doing this since 23/08.

A person decides, the system only records it: System Manager, reason mandatory, written to
the request history and to the package. Nothing is deleted, no package status changes, no
file is touched - a single flag makes the cron skip it, and "Thử lại tiếp" clears the flag
again if the provider document comes back. Deliberately not automatic: abandoning a signed
document is not a decision a scheduled job should take on its own.

Abandoned packages stay visible on the page, marked, with the reason and who decided. Hiding
them would remove the only way to review the decision or reverse it.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
