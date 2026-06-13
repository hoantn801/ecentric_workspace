# Copyright (c) 2026, eCentric
# EC Order Retry - durable per-order retry queue for transient Omisell pull
# failures (Hotfix B, 2026-06-13). Logic lives in services.order_retry /
# api_order_retry; this layer enforces the state machine.

import frappe
from frappe import _
from frappe.model.document import Document

# Documented status lifecycle:
#   Pending    - queued, due at next_retry_at
#   Processing - claimed by a worker (holds processing_token)
#   Completed  - targeted re-pull succeeded
#   Dead       - exhausted max_attempts; ToDo raised, not retried again
ACTIVE_RETRY_STATUSES = ("Pending", "Processing")
TERMINAL_RETRY_STATUSES = ("Completed", "Dead")

# Allowed transitions (worker + sanctioned service). Reactivating a TERMINAL
# item (Completed/Dead -> anything) is allowed ONLY via the requeue service,
# which sets frappe.flags.in_order_retry_transition. A generic Desk/API edit
# that tries it is rejected here.
_ALLOWED = {
    "Pending": {"Processing", "Pending", "Dead"},
    "Processing": {"Completed", "Pending", "Dead", "Processing"},
}


class ECOrderRetry(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if not before:
            return
        if getattr(frappe.flags, "in_order_retry_transition", False):
            return  # sanctioned internal/service-layer transition
        frm, to = before.status, self.status
        if frm == to:
            return
        if frm in TERMINAL_RETRY_STATUSES or to not in _ALLOWED.get(frm, set()):
            frappe.throw(
                _("Invalid EC Order Retry transition {0} -> {1}. Use the "
                  "order-retry service (retry_now / requeue / mark_dead).").format(frm, to),
                frappe.ValidationError)
