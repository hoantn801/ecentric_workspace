# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition cho Booking Request."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    BrandOptions, ExactAndDateFilters, ServiceMethod, service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.booking_request.application.service"

BOOKING_REQUEST_DEFINITION = ApprovalDefinition(
    code="BOOKING_REQUEST", business_doctype="EC Booking Request", feature="booking_request",
    editable_fields=("request_title", "brand", "brand_is_new", "brand_display_name",
                     "booking_owner", "account_owner", "booking_type", "kol_count",
                     "expected_budget", "campaign_start_date", "campaign_end_date",
                     "brand_brief", "request_attachment", "cc_to", "kol_list",
                     "department", "company"),
    my_request_fields=("name", "request_title", "brand", "booking_type", "expected_budget",
                       "campaign_start_date", "fulfillment_status",
                       "fulfillment_expected_date", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "brand", "booking_type", "expected_budget",
                          "campaign_start_date", "fulfillment_status",
                          "fulfillment_expected_date", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=BrandOptions((
        ("booking_types", ("KOL/KOC Chỉ định", "Middle KOL/KOC", "Massive")),
    )),
    filter_builder=ExactAndDateFilters(("booking_type", "brand", "fulfillment_status")),
    #: Danh sach KOL la NOI DUNG cua dot booking do; chep sang phieu moi la bung mot danh
    #: sach cu vao mot chien dich khac ma nguoi gui chua doc lai.
    clone_exclude_fields=("kol_list",),
    detail_extender=ServiceMethod(_BASE, "booking_block"),
    **service_callbacks("booking_request"))
