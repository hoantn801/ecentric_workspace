"""Stable compatibility API backed by the shared request application layer."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

# bind_fulfillment = bind(...) + list_fulfillment_queue / claim_fulfillment / complete_fulfillment /
# reassign (01/10/2026: buoc "Data xu ly" sau khi duyet) - moi cua doc van qua bind() -> can_view_request.
globals().update(bind_fulfillment(
    "DAILY_TARGET",
    ("name", "request_title", "requested_by", "request_scope", "brand", "target_month",
     "fulfillment_status", "fulfillment_owner", "fulfillment_due_at", "creation"),
    "creation asc"))
