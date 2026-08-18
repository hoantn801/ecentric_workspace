"""Stable compatibility API for Asset Request."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("ASSET_REQUEST",
    ("name", "request_title", "requested_by", "request_type", "asset_type", "quantity",
     "requested_needed_date", "operation_expected_completion_date", "fulfillment_status",
     "fulfillment_owner", "fulfillment_due_at"), "modified asc", operation_fields=True))
