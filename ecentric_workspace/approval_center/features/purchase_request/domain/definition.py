"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.features.purchase_request.application.service import purchase_title, validate_purchase
from ecentric_workspace.approval_center.shared.definition_support import DepartmentOptions, ExactAndDateFilters, StaticOptions


def _make(code, doctype, editable, mine, approvals, options, title, validator,
          manager=False, esign=False, draft_preparer=None):
    return ApprovalDefinition(
        code=code, business_doctype=doctype, editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        title_builder=title, filter_builder=ExactAndDateFilters(),
        submitter=Submitter(doctype, code, validator, title, manager, esign),
        resubmitter=Resubmitter(doctype, title), draft_preparer=draft_preparer)

PURCHASE_REQUEST_DEFINITION = _make(
    "PURCHASE_REQUEST", "EC Purchase Request",
    ("department", "justification", "purchase_details", "payment_amount", "payment_term",
     "payment_term_other", "supplier_type", "supplier_name", "new_supplier_information",
     "additional_notes_comments", "estimated_purchase_date", "estimated_delivery_date",
     "request_attachment", "company"),
    ("name", "request_title", "department", "payment_amount", "payment_term",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "department", "payment_amount", "payment_term", "creation"),
    DepartmentOptions((("payment_terms", ("Pay in advance 100%", "Pay within 7 days",
        "Pay within 14 days", "Pay within 30 days", "Other")),
        ("supplier_types", ("Existing supplier", "New supplier")))),
    purchase_title, validate_purchase, manager=True)


