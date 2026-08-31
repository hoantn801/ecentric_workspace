# Copyright (c) 2026, eCentric and contributors
"""Explicit, pure state machines for the esign layer (NO frappe import).

Two coordinated machines - never collapsed (three distinct concepts by design):
  * provider request accepted   -> DSR 'Provider Accepted'
  * provider signature verified -> DSR 'Signed'
  * approval level completed    -> DSR 'Approval Completed'
"""

PACKAGE = "package"
DSR = "dsr"

PACKAGE_STATES = (
    "Draft", "Locked", "Provider Creating", "Provider Created", "Active",
    "Provider Create Failed", "Superseded", "Cancelled", "Completed",
)
PACKAGE_TERMINAL = ("Superseded", "Cancelled", "Completed")

PACKAGE_TRANSITIONS = {
    "Draft": ("Locked", "Cancelled"),
    "Locked": ("Provider Creating", "Active", "Superseded", "Cancelled"),
    "Provider Creating": ("Provider Created", "Provider Create Failed", "Cancelled"),
    "Provider Created": ("Active",),
    "Provider Create Failed": ("Provider Creating", "Superseded", "Cancelled"),
    "Active": ("Completed", "Superseded", "Cancelled"),
    "Superseded": (),
    "Cancelled": (),
    "Completed": (),
}
# 'Locked' -> 'Active' directly covers the 'Before First Signing Level' creation
# trigger where provider creation happens later, inside the first sign worker.

DSR_STATES = (
    "Draft", "Prepared", "Queued", "Provider Accepted", "Verifying", "Signed",
    "Approval Completed", "Mapping Required", "Placement Required",
    "Retryable Failure", "Permanent Failure", "Verification Mismatch",
    "Manual Review", "Cancelled", "Rejected", "Superseded",
)
DSR_TERMINAL = ("Approval Completed", "Permanent Failure", "Cancelled", "Rejected", "Superseded")
DSR_LIVE = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Signed")

DSR_TRANSITIONS = {
    "Draft": ("Prepared", "Cancelled"),
    "Prepared": ("Queued", "Mapping Required", "Placement Required", "Cancelled", "Superseded"),
    "Queued": ("Provider Accepted", "Verifying", "Retryable Failure", "Permanent Failure",
               "Mapping Required", "Cancelled", "Superseded", "Signed",
               # Queued -> Verification Mismatch / Manual Review: hai canh nay THIEU tu dau,
               # nen mot chan ky ket o Queued la BAT TU: process_signing_request gap signer
               # da rejected thi nem InvalidTransition, sweep_stale don rac moi gio cung nem
               # not - va Queued khong nam trong _NEEDS_HUMAN nen trang ops khong hien no.
               # Ket + tang hinh + khong don duoc (BOT C, 31/08).
               "Verification Mismatch", "Manual Review"),
    # Queued -> Signed: poll-first found the signer already signed by a previous
    # uncertain attempt - never blind-resubmit.
    "Provider Accepted": ("Verifying", "Signed", "Retryable Failure", "Permanent Failure",
                          "Verification Mismatch", "Manual Review", "Cancelled", "Superseded"),
    "Verifying": ("Signed", "Verification Mismatch", "Retryable Failure", "Permanent Failure",
                  "Manual Review", "Cancelled", "Superseded"),
    "Signed": ("Approval Completed", "Manual Review"),
    # Signed -> Manual Review: engine state drifted between verification and
    # completion (engine.approve refused) - approval state is whatever the engine says.
    "Approval Completed": (),
    "Mapping Required": ("Prepared", "Cancelled", "Superseded"),
    "Placement Required": ("Prepared", "Cancelled", "Superseded"),
    "Retryable Failure": ("Queued", "Manual Review", "Permanent Failure", "Cancelled", "Superseded"),
    "Permanent Failure": (),
    "Verification Mismatch": ("Manual Review",),
    # Manual Review -> Signed: doi soat. Chan ky bi day sang day vi nha cung cap im lang; sau
    # do chu ky THAT xuat hien (nguoi ky tu lam tren portal). Doi soat CHI doc lai trang thai
    # ben nha cung cap va xac minh - khong bao gio gui lai lenh ky, vi lam vay se tao chu ky
    # thu hai. Xem api.reconcile_signature_request.
    "Manual Review": ("Queued", "Cancelled", "Approval Completed", "Signed",
                      # Manual Review -> Superseded: thieu canh nay thi create_revision
                      # (tra lai -> gui lai) NEM dung luc mot chan ky dang cho nguoi xu ly -
                      # tuc chu trinh sendback chet dung luc hay can no nhat (BOT C, 31/08).
                      "Superseded"),
    # Manual Review -> Approval Completed is the WINNER-REPAIR edge only (R2,
    # 2026-07-12): if a losing racer stamped Manual Review between the winner's
    # engine.approve and its final write, the winner upgrades the label to the
    # true terminal outcome. Terminal states themselves still have no exits -
    # Approval Completed can never be downgraded.
    "Cancelled": (),
    "Rejected": (),
    "Superseded": (),
}
# 'Rejected' is entered only at creation time (action=Reject audit rows), never
# from a live Sign chain - hence no inbound edges here.


class InvalidTransition(ValueError):
    pass


def _table(kind):
    if kind == PACKAGE:
        return PACKAGE_STATES, PACKAGE_TRANSITIONS
    if kind == DSR:
        return DSR_STATES, DSR_TRANSITIONS
    raise ValueError("unknown state-machine kind: %r" % kind)


def is_terminal(kind, status):
    return status in (PACKAGE_TERMINAL if kind == PACKAGE else DSR_TERMINAL)


def assert_transition(kind, from_status, to_status):
    """Raise InvalidTransition unless from->to is an allowed edge."""
    states, table = _table(kind)
    if from_status not in states:
        raise InvalidTransition("%s: unknown source state %r" % (kind, from_status))
    if to_status not in states:
        raise InvalidTransition("%s: unknown target state %r" % (kind, to_status))
    if to_status not in table[from_status]:
        raise InvalidTransition("%s: illegal transition %r -> %r" % (kind, from_status, to_status))
    return True
