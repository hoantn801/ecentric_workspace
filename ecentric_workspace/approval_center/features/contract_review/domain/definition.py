"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import (
    BrandAndDepartmentOptions, ExactAndDateFilters, service_callbacks,
)

CONTRACT_REVIEW_DEFINITION = ApprovalDefinition(
    code="CONTRACT_REVIEW", business_doctype="EC Contract Review Request", feature="contract_review",
    editable_fields=("request_title", "request_kind", "previous_request", "contract_type",
                     "request_type", "brand", "justification", "contract_value",
                     "contract_start_date", "contract_end_date", "request_details",
                     "cc_to", "request_attachment", "department", "company"),
    my_request_fields=("name", "request_title", "request_kind", "contract_type", "brand",
                       "contract_value", "expected_response_date", "approval_request",
                       "creation", "modified"),
    approval_list_fields=("name", "request_title", "request_kind", "contract_type", "brand",
                          "contract_value", "expected_response_date", "department", "creation"),
    status_labels=STANDARD_STATUS_LABELS,
    options_provider=BrandAndDepartmentOptions((
        ("request_kinds", ("Existing", "New")),
        ("contract_types", ("Purchase / Mua vào (EC)", "Sales / Bán ra (EC)",
                            "Service / Dịch vụ (GBSxBrand)")),
        ("request_types", ("Template from EC / Mẫu theo khung EC",
                           "Template from partner / Mẫu theo khung đối tác",
                           "New contract template / Hợp đồng mới")),
    )),
    filter_builder=ExactAndDateFilters(("contract_type", "request_kind")),
    **service_callbacks("contract_review"))
