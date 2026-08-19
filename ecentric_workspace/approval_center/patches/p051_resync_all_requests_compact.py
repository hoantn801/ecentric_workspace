# Copyright (c) 2026, eCentric and contributors
"""Re-sync the All Requests Web Page after the compact-table restyle (smaller font,
wider layout, vertical-align). Once-only patches don't re-run; a fresh patch is the
repo convention for pushing edited page HTML to the live Web Page on Frappe Cloud
deploy. Idempotent (upsert returns 'unchanged' if content matches)."""
from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    page_sync.sync()
