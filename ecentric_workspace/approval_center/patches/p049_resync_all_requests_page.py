# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Approval Center 'All requests' Web Page (/approvals/all-requests)
after its HTML was updated (Teams-style Đã nhận/Đã gửi tabs + sender/recipient
avatars, on top of the existing rich-filter layout).

p048 already ran on earlier deploys, so it will not re-execute; a fresh patch is
the repo's convention for pushing edited page HTML into the live Web Page on the
next `bench migrate` (i.e. on Frappe Cloud deploy) with no manual command.
Idempotent: page_sync.upsert_web_page returns 'unchanged' if content matches."""
from ecentric_workspace.approval_center.all_requests import page_sync


def execute():
    page_sync.sync()
