"""Stable compatibility API for System Request."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("SYSTEM_REQUEST",
    ("name", "request_title", "requested_by", "request_type", "priority",
     "requester_expected_resolution_date", "operation_expected_completion_date",
     "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"),
    "requester_expected_resolution_date asc", operation_fields=True))
