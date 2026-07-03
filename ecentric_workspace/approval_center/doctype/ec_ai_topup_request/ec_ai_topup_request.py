# Copyright (c) 2026, eCentric and contributors
"""EC AI Topup Request - AI Topup business data + fulfillment lifecycle.
Approval STATE lives on EC Approval Request (no approval_status/current_stage
here). This controller enforces business-intrinsic validation; orchestration is
in ecentric_workspace.approval_center.ai_topup.service."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

# Base evidence always needed to complete fulfillment.
_COMPLETION_BASE = ("actual_amount", "actual_currency", "topup_datetime",
                    "transaction_reference", "payment_proof", "invoice_status",
                    "confirmed_account_manager")
_LOCK_AFTER_COMPLETE = _COMPLETION_BASE + (
    "actual_ai_account", "actual_account_email", "actual_plan", "invoice_receipt",
    "no_invoice_reason", "completed_by", "completed_at")


class ECAITopupRequest(Document):
    def validate(self):
        self._validate_account_mode()
        self._validate_subscription_dates()
        self._finance_comment()
        self._department_snapshot_lock()
        self._fulfillment_needs_approval()
        self._completion()
        self._lock_completed_fields()

    # ---- request validation ----
    def _validate_account_mode(self):
        if self.account_mode == "Existing Account":
            if not self.ai_account:
                frappe.throw(_("Existing Account requests require an AI Account."))
            status = frappe.db.get_value("EC AI Account", self.ai_account, "status")
            if status and status != "Active":
                frappe.throw(_("AI Account {0} is not Active (status: {1}).").format(self.ai_account, status))
        elif self.account_mode == "New Account":
            missing = [f for f in ("ai_tool", "proposed_account_email", "proposed_account_manager")
                       if not self.get(f)]
            if missing:
                frappe.throw(_("New Account requests require: {0}").format(", ".join(missing)))
            require_active_system_user(self.proposed_account_manager, "proposed_account_manager")

    def _validate_subscription_dates(self):
        if self.subscription_start_date and self.subscription_end_date:
            if self.subscription_end_date < self.subscription_start_date:
                frappe.throw(_("Subscription end date cannot be before start date."))

    def _finance_comment(self):
        if (self.approved_amount is not None and self.requested_amount is not None
                and self.approved_amount != self.requested_amount
                and not (self.finance_adjustment_comment or "").strip()):
            frappe.throw(_("A finance comment is mandatory when approved_amount differs from requested_amount."))

    def _department_snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("department is a submission snapshot and cannot change after submission."))

    # ---- fulfillment lifecycle ----
    def _fulfillment_needs_approval(self):
        if self.fulfillment_status in ("Assigned", "In Progress", "Completed"):
            appr = self.approval_request and frappe.db.get_value(
                "EC Approval Request", self.approval_request, "approval_status")
            if appr != "Approved":
                frappe.throw(_("Fulfillment cannot start before the request is fully Approved."))

    def _completion(self):
        if self.fulfillment_status != "Completed":
            return
        missing = [f for f in _COMPLETION_BASE if not self.get(f)]
        # account identity: either an existing account link or the actual email
        if not (self.actual_ai_account or self.actual_account_email):
            missing.append("actual_ai_account/actual_account_email")
        # invoice conditional rules
        if self.invoice_status == "Invoice Available" and not self.invoice_receipt:
            missing.append("invoice_receipt")
        if self.invoice_status == "No Invoice Issued" and not (self.no_invoice_reason or "").strip():
            missing.append("no_invoice_reason")
        if missing:
            frappe.throw(_("Cannot complete: missing fulfillment evidence: {0}").format(", ".join(missing)))
        if not self.completed_by:
            self.completed_by = frappe.session.user
        if not self.completed_at:
            self.completed_at = frappe.utils.now_datetime()

    def _lock_completed_fields(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if before and before.fulfillment_status == "Completed":
            for f in _LOCK_AFTER_COMPLETE:
                if (self.get(f) or None) != (before.get(f) or None):
                    frappe.throw(_("Completed fulfillment fields are locked; use an audited System Manager correction."))
