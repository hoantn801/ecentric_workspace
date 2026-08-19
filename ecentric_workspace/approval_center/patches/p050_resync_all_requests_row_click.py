# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Approval Center 'All requests' Web Page after the row-interaction
update (removed the 'Mở' column; the whole row is now clickable to open detail).

Once-only patches don't re-run, so a fresh patch is the repo convention for pushing
edited page HTML into the live Web Page on the next bench migrate (Frappe Cloud deploy)
with no manual command. Idempotent: upsert returns 'unchanged' if content matches."""
from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    page_sync.sync()
