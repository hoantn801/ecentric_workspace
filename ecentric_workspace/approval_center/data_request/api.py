"""Stable compatibility API for Data Request."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("DATA_REQUEST",
    ("name", "request_title", "requested_by", "request_type", "urgency", "importance",
     "expected_resolution_date", "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"),
    "expected_resolution_date asc"))
