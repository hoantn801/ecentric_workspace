# Copyright (c) 2026, eCentric and contributors
"""Re-sync the All Requests Web Page after turning it into the approval hub:
adds the 'Chờ tôi xử lý' (fulfillment queue) tab and per-row quick actions
(Duyệt / Từ chối / Nhận xử lý). Once-only patches don't re-run, so edited page HTML needs
a fresh patch to reach the live Web Page on the next Frappe Cloud deploy. Idempotent."""
from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    page_sync.sync()
