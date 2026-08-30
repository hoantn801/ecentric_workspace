# Copyright (c) 2026, eCentric and contributors
"""Publish the "Chân ký cần can thiệp" admin page at /ec-esign/ops.

Every rescue path for a failed signing leg already existed and worked: retry, reconcile a leg
parked in Manual Review, reconcile an ambiguous document creation, fetch the signed PDF by
hand, resolve a hash mismatch. Not one of them was reachable from any screen. They ran only
if somebody typed an API call.

The consequence, from the 29/08 review: `Permanent Failure` and `Cancelled` have no outgoing
edge in the state machine, and the idempotency key is unique, so a fresh leg cannot be
created either. A request parked there was stuck for good, and every signing incident had to
come back to whoever wrote the system.

The page is read-only by itself - `ops_inbox` and each action assert System Manager on their
own. No button on it re-sends a signing command, so it can never produce a second signature.

It also surfaces what the 30-minute retrieval cron hides: the attempt count. An endlessly
retrying package and a package waiting normally look identical today; on 29/08 two packages
had spun over thirty times on a 404 with nobody aware.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
