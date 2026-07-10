# Copyright (c) 2026, eCentric and contributors
"""Create/refresh the Approval Center Operations Dashboard Web Page (/approvals/dashboard).
Idempotent. Does not touch the /approvals catalog page or any catalog card."""
from ecentric_workspace.approval_center.dashboard import page_sync


def execute():
    page_sync.sync()
