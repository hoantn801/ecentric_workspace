"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.features.affiliate_bonus.application.service import affiliate_title, validate_affiliate
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

AFFILIATE_BONUS_DEFINITION = _make(
    "AFFILIATE_BONUS_REQUEST", "EC Affiliate Bonus Request",
    ("service_month", "detail", "total_amount", "budget", "request_attachment", "department", "company"),
    ("name", "request_title", "service_month", "total_amount", "budget", "approval_request", "creation", "modified"),
    ("name", "request_title", "service_month", "total_amount", "budget", "creation"),
    StaticOptions(), affiliate_title, validate_affiliate)


