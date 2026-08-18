# Copyright (c) 2026, eCentric and contributors
"""Create/refresh the Approval Center 'All requests' Web Page (/approvals/all-requests).
Idempotent; does not touch other Approval Center pages."""
from ecentric_workspace.approval_center.all_requests import page_sync


def execute():
    page_sync.sync()
