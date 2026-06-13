"""Adaptive sub-window split math for the Omisell order pull (scalability
mini-phase, 2026-06-14). PURE: no frappe, no I/O, no DB - just the split
decision, the deterministic midpoint, the half-open epoch seam, and the
single source of truth for the stop-state constants. Unit-testable on its own.

Boundary contract (Remote API boundary semantics unknown; adjacent API queries
intentionally share the boundary instant to avoid gaps):
we model OUR logical windows as half-open `[a, b)` internally (for checkpoint
ownership), but we send the list API the boundary UNCHANGED - no +1/-1. When a
window is split at `mid`, the two API queries SHARE the seam:
    left  -> updated_from=epoch(a),   updated_to=epoch(mid)
    right -> updated_from=epoch(mid), updated_to=epoch(b)
Because Omisell's updated_from/updated_to inclusivity is UNVERIFIED (diagnostic
46/47), this shared boundary is safe under BOTH backends:
  * inclusive `[from, to]`  -> an order exactly at `mid` is read by BOTH
    children and de-duplicated downstream by `order_key` (a harmless double
    read, never a double business record);
  * half-open `[from, to)`  -> the seam order is read by exactly one child.
Either way NO second is skipped. We deliberately prefer a POSSIBLE duplicate
read over a gap that would silently drop the boundary order. `order_key` dedupe
is the safety net for the seam overlap, NOT a substitute for the boundary
design. (Earlier we used `updated_to = epoch(b) - 1`; that is UNSAFE under a
half-open API - it drops the `b-1` second - so it was removed.)
"""
from datetime import timedelta

# ---- stop-state constants (single source of truth; orchestrator + tests) ----
COMPLETED = "completed"                          # leaf fully processed
SPLIT_REQUIRED = "split_required"                # listed/count > cap -> divide
BUDGET_EXHAUSTED = "budget_exhausted"            # ran out of brand time budget
MINIMUM_WINDOW_CAPPED = "minimum_window_capped"  # min width still > cap (stuck)
RETRY_PERSISTENCE_FAILED = "retry_persistence_failed"  # EC Order Retry write failed
PROCESSING_FAILED = "processing_failed"          # auth/list/system failure

STOP_STATES = (COMPLETED, SPLIT_REQUIRED, BUDGET_EXHAUSTED, MINIMUM_WINDOW_CAPPED,
               RETRY_PERSISTENCE_FAILED, PROCESSING_FAILED)

# A leaf is "done" (checkpoint may advance to its end) ONLY for COMPLETED.
ADVANCEABLE_STATES = (COMPLETED,)

DEFAULT_MIN_SUBWINDOW_SECONDS = 300   # 5 min
DEFAULT_MAX_SPLIT_DEPTH = 6
DEFAULT_BRAND_BUDGET_SECONDS = 3000


def window_seconds(cf, ct):
    """Width of [cf, ct) in whole seconds (datetimes)."""
    return int((ct - cf).total_seconds())


def can_split(width_seconds, depth, min_seconds, max_depth):
    """Split ONLY when strictly wider than the minimum AND below the max depth.
    Condition (binding): width > min_window AND depth < max_depth."""
    return width_seconds > int(min_seconds) and depth < int(max_depth)


def split_point(cf, ct):
    """Deterministic midpoint in WHOLE seconds, strictly between cf and ct for
    any window >= 2s (guaranteed: we only ever split windows wider than
    min_subwindow = 300s). Left child = [cf, mid), right child = [mid, ct)."""
    return cf + timedelta(seconds=window_seconds(cf, ct) // 2)


def api_upper_bound(epoch_to):
    """Upper bound to send the list API for a logical window ending at `to`:
    pass epoch(to) UNCHANGED (no +1/-1). SHARED-BOUNDARY contract - adjacent
    queries share the seam instant so no second can be skipped regardless of the
    API's (unknown) inclusivity. If inclusive, the seam order is read by both
    children and de-duplicated by order_key; if half-open, by exactly one.
    Prefer a possible duplicate read over a data-loss gap."""
    return int(epoch_to)
