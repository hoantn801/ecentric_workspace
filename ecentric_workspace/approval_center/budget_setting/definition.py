"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.budget_setting.service import budget_title, validate_budget
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

BUDGET_SETTING_DEFINITION = _make(
    "BUDGET_SETTING", "EC Budget Setting Request",
    ("budget_period_type", "period_start", "department", "approved_budget_current_period",
     "actual_spending_current_period", "forecast_budget_next_period", "forecast_justification",
     "has_financial_risks", "financial_risk_details", "additional_notes_comments",
     "request_attachment", "company"),
    ("name", "request_title", "budget_period_type", "period_start", "department",
     "forecast_budget_next_period", "approval_request", "creation", "modified"),
    ("name", "request_title", "budget_period_type", "period_start", "department",
     "forecast_budget_next_period", "creation"),
    DepartmentOptions((("budget_period_types", ("Annual", "Monthly")), ("yes_no", ("Yes", "No")))),
    budget_title, validate_budget)


