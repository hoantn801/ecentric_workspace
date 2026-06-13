"""Alert Case lifecycle - SINGLE SOURCE OF TRUTH for statuses (Step 1, 2026-06-13).

One canonical definition of active vs terminal statuses + the allowed
transition matrix. Every module (engine, api_alerts, api_repair, controller)
imports from HERE - no ad-hoc status lists may be duplicated elsewhere.

Canonical model (decision D1, locked):
  ACTIVE   = Open, In Review            -> may receive new occurrences
  TERMINAL = Closed, Ignored, Cancelled -> frozen; never receive occurrences

Transitional compatibility: legacy `Resolved` (the old completed status,
being migrated to `Closed` by patch p002) is READ as terminal so a
half-migrated DB never lets a Resolved case re-accept evidence. No new
record may be WRITTEN as Resolved (api_alerts forbids it; engine never
emits it). After p002 + a later cleanup phase, LEGACY_TERMINAL empties.

PURE module (frappe-free) so the rules are unit-testable anywhere.
"""

ACTIVE_STATUSES = ("Open", "In Review")
TERMINAL_STATUSES = ("Closed", "Ignored", "Cancelled")
# legacy completed status, transitional read-compat only (never written)
LEGACY_TERMINAL = ("Resolved",)

ALL_TERMINAL = TERMINAL_STATUSES + LEGACY_TERMINAL

# Terminal statuses whose set_status requires a note/reason (server-enforced).
NOTE_REQUIRED_STATUSES = ("Closed", "Ignored", "Cancelled")

# KAM/Manager normal transitions (api_alerts.set_status). Cancelled is NOT
# here - it is supervisor-only via a separate endpoint and never reopens.
NORMAL_TRANSITIONS = {
    "Open": ("In Review", "Closed", "Ignored"),
    "In Review": ("Closed", "Ignored"),
}

# Supervisor-only transitions (api_alerts.cancel_case). Reason required.
CANCEL_FROM = ("Open", "In Review")


def is_active(status):
    return status in ACTIVE_STATUSES


def is_terminal(status):
    """True for Closed/Ignored/Cancelled AND legacy Resolved (read-compat)."""
    return status in ALL_TERMINAL


def can_receive_occurrence(status):
    """Only Open / In Review. Closed/Ignored/Cancelled/legacy-Resolved = no."""
    return is_active(status)


def can_transition(from_status, to_status):
    """Allowed NORMAL (KAM) transition? No reopen of terminal cases in this
    phase. Same-state is a no-op (allowed, idempotent)."""
    if from_status == to_status:
        return True
    return to_status in NORMAL_TRANSITIONS.get(from_status, ())


def can_cancel(from_status):
    """A case may be Cancelled only from an active state (supervisor-only;
    permission is enforced in the API layer, not here)."""
    return from_status in CANCEL_FROM
