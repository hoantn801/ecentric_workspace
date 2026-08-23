"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.features.payment_request.application.service import normalize_payment, payment_title, validate_payment
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

PAYMENT_REQUEST_DEFINITION = _make(
    "PAYMENT_REQUEST", "EC Payment Request",
    ("request_title", "reason", "payment_amount", "payment_date", "payee_full_name",
     "account_bank", "bank_account_number", "has_purchase_request", "purchase_request",
     "no_purchase_request_reason", "is_cost_valid", "details_and_attachments_correct",
     "request_attachment", "department", "company"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date",
     "approval_request", "creation", "modified"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date", "creation"),
    StaticOptions((("yes_no", ("Yes", "No")),)), payment_title, validate_payment,
    manager=True, esign=True, draft_preparer=normalize_payment)


