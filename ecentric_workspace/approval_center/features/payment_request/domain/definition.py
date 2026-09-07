"""Module-owned immutable approval definition."""
from ecentric_workspace.approval_center.shared.requests.contracts import ApprovalDefinition, STANDARD_STATUS_LABELS
from ecentric_workspace.approval_center.shared.finance_support import Resubmitter, Submitter
from ecentric_workspace.approval_center.features.payment_request.application.service import (
    installments_block, normalize_payment, payment_title, validate_payment)
from ecentric_workspace.approval_center.shared.definition_support import DepartmentOptions, ExactAndDateFilters, StaticOptions


def _make(code, doctype, editable, mine, approvals, options, title, validator,
          manager=False, esign=False, draft_preparer=None, detail_extender=None):
    return ApprovalDefinition(
        # `feature` la duong dan module ma fulfillment_service.claim/complete import
        # (features.<feature>.application.service). Thieu no thi buoc 6 "Finance xu ly UNC"
        # khong goi duoc (07/09).
        code=code, business_doctype=doctype, feature="payment_request", editable_fields=editable,
        my_request_fields=mine, approval_list_fields=approvals,
        status_labels=STANDARD_STATUS_LABELS, options_provider=options,
        title_builder=title, filter_builder=ExactAndDateFilters(),
        submitter=Submitter(doctype, code, validator, title, manager, esign),
        resubmitter=Resubmitter(doctype, title), draft_preparer=draft_preparer,
        detail_extender=detail_extender,
        # O tich "Toi xac nhan thong tin va tep dinh kem la chinh xac" la mot CAM KET CA
        # NHAN. Chep no sang phieu moi la ky thay nguoi dung cho mot bo ho so ho chua doc
        # lai - nguoi de nghi phai tu tich lai.
        clone_exclude_fields=("details_and_attachments_correct",))

PAYMENT_REQUEST_DEFINITION = _make(
    "PAYMENT_REQUEST", "EC Payment Request",
    ("request_title", "reason", "payment_amount", "payment_date", "payee_full_name",
     "account_bank", "bank_account_number", "has_purchase_request", "purchase_request",
     "funding_source_doctype", "funding_source_name",
     "no_purchase_request_reason", "is_cost_valid", "details_and_attachments_correct",
     "request_attachment", "department", "company",
     # chia dot (07/09): installment_no / installment_of do SERVER dat, KHONG cho client sua
     "payment_mode", "total_amount", "next_installment_amount", "next_installment_date"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date",
     "approval_request", "fulfillment_status", "payment_mode", "installment_no", "installment_of",
     "creation", "modified"),
    ("name", "request_title", "payee_full_name", "payment_amount", "payment_date", "creation"),
    StaticOptions((("yes_no", ("Yes", "No")),)), payment_title, validate_payment,
    manager=True, esign=True, draft_preparer=normalize_payment,
    detail_extender=installments_block)


