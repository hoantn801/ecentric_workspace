# Copyright (c) 2026, eCentric and contributors
"""Re-publish the ops page so signature debts show up on it.

Settled 31/08: when the signing gate is off, an approver pressing plain "Duyệt" completes a
level that policy says must be signed. Until now that happened in complete silence - no
signature, no warning, not one line saying the level was approved while signing was off.
Months later the request looks exactly like a fully signed one.

The request is allowed to continue and to reach Approved even while a level owes its
signature; that was the operational call. The trade is that the debt has to be VISIBLE. A
debt nobody can see is a debt nobody ever settles - so the ops page now lists them, and
flags the ones on already-approved requests, which are the easiest to forget.

Only the person who approved can settle their own debt. Nobody signs on anyone's behalf.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
