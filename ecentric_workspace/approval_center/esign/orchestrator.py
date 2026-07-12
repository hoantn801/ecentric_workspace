# Copyright (c) 2026, eCentric and contributors
"""Provider orchestration entry points (governed).

These are the named, reusable entry points S2B-A requires. They wrap the proven
state-aware worker (esign.tasks) and completion path (esign.service) with an explicit
reload-under-lock + persisted-state verification, so callers (scheduler, manual ops
action, future callback re-poll) share ONE governed path:

    submit_provider_request(dsr_name)  - poll-first, binding-gated single bulk-process
    poll_provider_request(dsr_name)    - poll + verify + reconcile toward completion

Invariants (delegated to the reused services, never re-implemented here):
  * reload + lock the DSR, verify persisted state before acting;
  * idempotency keys + POLL-FIRST prevent duplicate SCTS submission;
  * the pre-write binding gate (esign.binding) runs before any bulk-process write;
  * governed immutable events are appended by the reused service on every transition;
  * terminal DSR states are preserved (conditional writes; never downgraded);
  * the Approval Engine is completed ONLY after a verified Document/{id} status
    (esign.service.verify_and_complete via the engine-side guard).
"""
import frappe

from ecentric_workspace.approval_center.esign import service as svc
from ecentric_workspace.approval_center.esign import tasks

DSR = "EC Digital Signature Request"
SUBMIT_ELIGIBLE = ("Queued", "Provider Accepted", "Verifying")
IN_FLIGHT = ("Queued", "Provider Accepted", "Verifying")


def submit_provider_request(dsr_name):
    """Governed submit. Reload+lock, verify submit-eligible persisted state, then run the
    worker (which creates the provider document if needed, polls first, enforces the
    binding gate, submits bulk-process at most once, and re-polls). Terminal or
    ineligible states are idempotent no-ops - never a blind resubmission."""
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    st = frappe.db.get_value(DSR, dsr_name, "status")
    if st not in SUBMIT_ELIGIBLE:
        return {"submitted": False, "reason": "not_submit_eligible", "status": st}
    tasks.process_signing_request(dsr_name)
    return {"submitted": True, "status": frappe.db.get_value(DSR, dsr_name, "status")}


def poll_provider_request(dsr_name):
    """Governed poll + reconcile. 'Signed' -> verified completion; in-flight -> poll-first
    worker; terminal/ineligible -> idempotent no-op. Completion never occurs without a
    verified provider Document status (enforced downstream)."""
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    st = frappe.db.get_value(DSR, dsr_name, "status")
    if st == "Signed":
        return svc.verify_and_complete(dsr_name)
    if st in IN_FLIGHT:
        tasks.process_signing_request(dsr_name)
        return {"polled": True, "status": frappe.db.get_value(DSR, dsr_name, "status")}
    return {"polled": False, "reason": "terminal_or_ineligible", "status": st}
