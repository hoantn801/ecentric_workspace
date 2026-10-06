"""Module-owned immutable approval definition."""
from dataclasses import replace as _dc_replace
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.definition_support import (
    DepartmentRows, ExactAndDateFilters, StaticOptions, service_callbacks,
)


def _make(code, doctype, feature, editable, mine, approvals, options, filters=()):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, feature=feature, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        filter_builder=ExactAndDateFilters(filters), **service_callbacks(feature))

RESIGNATION_DEFINITION = _make(
    "RESIGNATION", "EC Resignation Request", "resignation",
    ("request_title", "resignation_for", "employee_email", "personal_email", "last_working_day",
     "resignation_reason", "workplace_environment_rating", "benefit_policy_rating",
     "corporate_culture_rating", "recommend_to_friend", "final_message", "department", "company"),
    ("name", "request_title", "resignation_for", "resignation_reason", "last_working_day",
     "fulfillment_status", "approval_request", "creation", "modified"),
    ("name", "request_title", "resignation_for", "resignation_reason", "last_working_day",
     "fulfillment_status", "department", "creation"),
    StaticOptions((("resignation_for", ("Myself", "Request for the others")),
       ("resignation_reasons", ("Unsuitable environment", "Have another direction",
          "Cultural Environment", "Personal Matters (Family, Myself,...)")),
       ("ratings", ("5 (Very satisfied)", "4 (Satisfied)", "3 (Neutral)",
                    "2 (Dissatisfied)", "1 (Very dissatisfied)")),
       ("recommend_options", ("Yes", "No", "Maybe")))),
    ("resignation_reason",))


# "Cho toi duyet" tren dien thoai (06/10/2026): the duyet nhanh hien cac cap nay. Chi truong
# nguoi duyet von xem duoc o trang chi tiet; khong dua luong ca nhan.
RESIGNATION_DEFINITION = _dc_replace(
    RESIGNATION_DEFINITION,
    quick_summary=(
        ("Đối tượng", "resignation_for"),
        ("Ngày làm cuối", "last_working_day"),
        ("Lý do", "resignation_reason"),
    ),
)
