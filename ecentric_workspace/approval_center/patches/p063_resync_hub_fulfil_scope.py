# Copyright (c) 2026, eCentric and contributors
"""Re-sync the All Requests hub page after scoping the 'Chờ tôi xử lý' tab to the current
user and showing the fulfillment state (Chờ nhận xử lý / Đang xử lý + owner) in that tab.
Once-only patches don't re-run, so edited page HTML needs a fresh patch. Idempotent."""
from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    page_sync.sync()
