# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Approval Center Dashboard Web Page after removing the 'Mở' column
(whole-row click to open detail, consistent with All Requests), compacting the table
and fixing cell vertical alignment. page_sync.sync() honours the #144 drift lock; the
prior live sha (10ea6e18) is now in SUPERSEDES_SHA256 so the shipped HTML writes once."""
from ecentric_workspace.approval_center.ui.dashboard import page_sync


def execute():
    page_sync.sync()
