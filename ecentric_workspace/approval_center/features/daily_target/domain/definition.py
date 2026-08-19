"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    STANDARD_STATUS_LABELS,
)
from ecentric_workspace.approval_center.shared.definition_support import (
    ExactAndDateFilters,
    StaticOptions,
    service_callbacks,
)


def _definition(code, doctype, feature, editable, mine, approvals, options=(), filters=(), title=False):
    return ApprovalDefinition(
        code=code,
        business_doctype=doctype,
        editable_fields=editable,
        my_request_fields=mine,
        approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS,
        options_provider=StaticOptions(options),
        filter_builder=ExactAndDateFilters(filters),
        **service_callbacks(feature, title=title),
    )

DAILY_TARGET_DEFINITION = _definition(
    "DAILY_TARGET", "EC Daily Target Request", "daily_target",
    ("request_title", "request_scope", "brand", "channels", "channel_other", "target_month",
     "target_setting_type", "justification", "request_attachment",
     "linked_project_level_requests", "department", "company"),
    ("name", "request_title", "request_scope", "brand", "target_month", "target_setting_type",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "request_scope", "brand", "target_month", "target_setting_type",
     "department", "creation"),
    options=(("scopes", ("Project level", "Consolidated / Total")),
             ("channels", ("Lazada", "Shopee", "TikTok Shop", "Other")),
             ("target_setting_types", ("Setting new target", "Revising current target"))),
    filters=("request_scope",),
)



