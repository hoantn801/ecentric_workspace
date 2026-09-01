# Copyright (c) 2026, eCentric and contributors
"""Re-publish the document/signing section: the per-document progress was reading the drawer.

`document_signing_section.html` declared TWO functions called `progressText` inside the same
IIFE - one at line 204 taking a document, one at line 479 taking nothing and reading the
signature drawer's state. Function declarations hoist, so the later one overwrote the earlier,
and every `progressText(d)` call in the document row silently ran the drawer's version:
argument ignored, numbers taken from `DRW.st`.

On screen the document row therefore showed the DRAWER's progress, which on a fresh page load
is "0/0". An approver opening a request with all five signature slots configured saw
"Đã thiết lập · 0/0" and could reasonably conclude nobody had set up any signatures. The
section header, which reads a different source, said 5/5 at the same time.

No error, no 500, no failing test - just a wrong number on a screen used to approve payments.
Found 02/09 while running the E2E by hand.

The document one is now `docProgressText`. A QC gate
(`test_no_shadowed_functions_in_iife.py`) fails on any two same-named function declarations at
the top level of one <script>, so the class of bug cannot come back unnoticed.

Separate patch because p118 and p119 have already run on production, and a patch runs ONCE.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
