"""Stable compatibility API backed by the shared request application layer.

28/09/2026: Hiring co them buoc "HR tuyen dung" sau khi CEO duyet (hang doi cua Role
EC Recruiter) -> dung `bind_fulfillment` nhu cac form co buoc xu ly khac."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

# bind_fulfillment = bind(...) + list_fulfillment_queue / claim_fulfillment / complete_fulfillment /
# reassign: moi cua doc van qua bind() -> can_view_request, giong payment_request.
globals().update(bind_fulfillment(
    "HIRING_REQUEST",
    ("name", "request_title", "requested_by", "position", "department", "number_of_vacancy",
     "employment_type", "fulfillment_status", "fulfillment_owner", "fulfillment_due_at",
     "creation"),
    "creation asc"))
