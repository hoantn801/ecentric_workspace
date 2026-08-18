# Copyright (c) 2026, eCentric and contributors
"""Pure step resolution for the Payment Request flow (NO frappe import, NO DB read).

``current_step`` takes statuses the CALLER already read from the DB (package status,
DSR status + its actor_type) and names which declared Step they sit in. It never reads
or writes anything itself - callers such as ``ui_state`` / ``inbox`` stay the ones
authoritative for what those statuses actually are; this module only removes the need
to re-derive "which stage is this" ad hoc at every call site.

Deliberately NOT covered: pinpointing which of document_setup/placement/package_lock a
Draft package is in before any DSR exists. That distinction already has a real,
authoritative reader (``document_setup.get_document_setup_state`` /
``placement_service.placement_state``); duplicating it here in a stateless function
would be a second, weaker source of the same fact. When no DSR exists yet, this
resolver returns the earliest pre-signing step as a safe default and says so.
"""
from ecentric_workspace.platform.esign.flow.payment_request import STEP_BY_ID

_ACTOR_STEP = {"Requester": "requester_sign", "Approver": "approver_sign"}


def current_step(package_status=None, dsr_status=None, dsr_actor_type=None):
    """Returns {"step": Step, "parked": bool, "reason": str|None}.

    dsr_actor_type: "Requester" or "Approver" (EC Digital Signature Request.actor_type).
    Required whenever dsr_status is given - the same DSR states are reachable from two
    different steps and only actor_type disambiguates them.
    """
    if dsr_status:
        actor_step_id = _ACTOR_STEP.get(dsr_actor_type)
        if not actor_step_id:
            raise ValueError(
                "dsr_actor_type must be 'Requester' or 'Approver' when dsr_status is given "
                "(got %r)" % dsr_actor_type)
        actor_step = STEP_BY_ID[actor_step_id]
        verify_step = STEP_BY_ID["verify"]

        if dsr_status in actor_step.park:
            return {"step": actor_step, "parked": True, "reason": dsr_status}
        if dsr_status in actor_step.dsr_entry:            # Draft / Prepared
            return {"step": actor_step, "parked": False, "reason": None}
        if dsr_status in verify_step.dsr_entry or dsr_status == verify_step.dsr_exit:
            # Queued / Provider Accepted / Verifying / Signed
            return {"step": verify_step, "parked": False, "reason": None}
        if dsr_status == actor_step.dsr_exit:              # Approval Completed
            return {"step": actor_step, "parked": False, "reason": None}
        raise ValueError("dsr_status %r is not reachable from %s (check esign.state / this "
                         "flow for drift)" % (dsr_status, actor_step_id))

    # No DSR yet: package-only stage. Cannot distinguish document_setup / placement /
    # package_lock from status alone (all three sit in "Draft") - see module docstring.
    if package_status in ("Locked", "Provider Creating", "Provider Created"):
        return {"step": STEP_BY_ID["provider_create"], "parked": False, "reason": None}
    if package_status == "Provider Create Failed":
        return {"step": STEP_BY_ID["provider_create"], "parked": True, "reason": package_status}
    if package_status == "Active":
        return {"step": STEP_BY_ID["retrieve_signed"], "parked": False, "reason": None}
    return {"step": STEP_BY_ID["document_setup"], "parked": False,
            "reason": "pre_signing_stage_undetermined"}
