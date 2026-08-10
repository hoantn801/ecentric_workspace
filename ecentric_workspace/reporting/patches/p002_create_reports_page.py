# Copyright (c) 2026, eCentric and contributors
"""Create/refresh the /reports hub Web Page on migrate (idempotent)."""
from ecentric_workspace.reporting.reports_hub import page_sync


def execute():
    page_sync.sync()
