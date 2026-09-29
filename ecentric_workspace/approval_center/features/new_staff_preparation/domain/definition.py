# Copyright (c) 2026, eCentric and contributors
"""Module-owned immutable approval definition cho New Staff Preparation (28/09/2026)."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition, STANDARD_STATUS_LABELS)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters, ServiceMethod, StaticOptions, service_callbacks,
)

_BASE = "ecentric_workspace.approval_center.features.new_staff_preparation.application.service"

NEW_STAFF_PREPARATION_DEFINITION = ApprovalDefinition(
    code="NEW_STAFF_PREPARATION", business_doctype="EC New Staff Preparation",
    feature="new_staff_preparation",
    #: Phieu TU TAO tu Offer da duyet. HR chi chinh duoc loi gioi thieu va ngay onboard
    #: (khi bi "Yeu cau bo sung" hoac qua `update_welcome`); phan con lai la ban chup Offer.
    editable_fields=("welcome_intro", "onboard_date"),
    my_request_fields=("name", "request_title", "candidate_name", "position", "department",
                       "onboard_date", "offer_request", "approval_request", "creation", "modified"),
    approval_list_fields=("name", "request_title", "candidate_name", "position", "department",
                          "onboard_date", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=StaticOptions(()),
    filter_builder=ExactAndDateFilters(("offer_request",)),
    draft_preparer=ServiceMethod(_BASE, "prepare_draft"),
    detail_extender=ServiceMethod(_BASE, "nsp_block"),
    **service_callbacks("new_staff_preparation"))
