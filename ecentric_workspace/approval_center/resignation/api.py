"""Stable compatibility API for Resignation Request."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("RESIGNATION",
    ("name", "request_title", "requested_by", "resignation_for", "resignation_reason",
     "last_working_day", "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"),
    "last_working_day asc"))
