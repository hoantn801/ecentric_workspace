# Copyright (c) 2026, eCentric and contributors
"""EC AI Topup Request - AI Topup business data ONLY. Approval STATE lives on
EC Approval Request; this doc has no approval_status/current_stage. Keeps its
own fulfillment lifecycle (a separate business concern after approval)."""
import frappe
from frappe import _
from frappe.model.document import Document

_COMPLETION = ("actual_account", "actual_tool_package", "actual_amount", "actual_currency",
               "topup_datetime", "transaction_reference", "payment_proof", "invoice_receipt")


class ECAITopupRequest(Document):
    def validate(self):
        self._finance_comment()
        self._department_snapshot_lock()
        self._completion()
        self._lock_completed_fields()

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

    def _completion(self):
        if self.fulfillment_status == "Completed":
            missing = [f for f in _COMPLETION if not self.get(f)]
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
            for f in _COMPLETION + ("completed_by", "completed_at"):
                if (self.get(f) or None) != (getattr(before, f, None) or None):
                    frappe.throw(_("Completed fulfillment fields cannot be altered."))
