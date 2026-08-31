# Copyright (c) 2026, eCentric and contributors
"""Re-publish the ops page: signature debts can now be closed, and the retry column counts
cron rounds instead of file reads.

Three things landed on the page at once:

1. Settle buttons. `signature_settled_at` existed on the level and the ops list already
   filtered on it, but nothing ever wrote to it - the debt list could only grow. It is closed
   by a person, not by the system: `da ky bu` (the approver signed on the SCTS portal) or
   `mien` (nobody can sign it any more), reason mandatory, written to the request history.
   There is deliberately no path that signs on someone's behalf.
2. The retry column said "da thu N lan" while N was the number of file reads, so a package
   holding three PDFs looked three times as broken as one holding a single PDF. It now
   counts cron rounds - the number the 30-minute schedule actually produced.
3. The bundle list stopped hiding Completed packages, so a finished package whose signed PDF
   never came back is visible instead of being retried forever off-screen.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
