"""PURE catch-up chunk planner (fix 2026-06-12).

Bug it fixes (LOF-VN): adaptive chunking lowered chunk_seconds to 1800 but
the chunk-count cap stayed fixed at 12, so one run spanned at most
12 x 30m = 6h - exactly the overlap window - and a stale last_sync_at could
NEVER catch up to `now`. Worse, caught_up was count-based
(chunks_done == chunks_planned) so a truncated run still reported
caught_up=true while the checkpoint silently stalled.

Fix: cap work per run by SPAN (default 12h = the same work bound the old
12 x 1h cap expressed), compute the required chunk count from the actual
window, and report `truncated` so the caller can set caught_up correctly
and expose next_from / remaining_seconds.

This module is frappe-free on purpose (math + datetime only) so the
planning rules are unit-testable anywhere.
"""
import math
from datetime import timedelta


def plan(start, end, chunk_seconds, min_chunks, span_seconds):
    """Plan catch-up chunks for [start, end].

    chunk_seconds: window size per chunk (>= 1).
    min_chunks:    caller's requested minimum (legacy max_chunks arg).
    span_seconds:  hard cap on TOTAL span this run may cover.

    Returns dict:
      chunks            [(from, to), ...] contiguous, each <= chunk_seconds
      required_chunks   ceil((end-start)/chunk_seconds)
      span_cap_chunks   span_seconds // chunk_seconds (>=1)
      eff_chunks        the cap actually applied
      planned_end       end of the last planned chunk (== end when not truncated)
      truncated         True when planned_end < end (run cannot reach `end`)
    """
    if not start or not end or end <= start:
        return {"chunks": [], "required_chunks": 0, "span_cap_chunks": 0,
                "eff_chunks": 0, "planned_end": start, "truncated": False}
    cs = max(1, int(chunk_seconds))
    total = (end - start).total_seconds()
    required = max(1, int(math.ceil(total / cs)))
    span_cap = max(1, int(span_seconds // cs))
    eff = min(max(int(min_chunks or 1), required), span_cap)
    chunks, cur = [], start
    while cur < end and len(chunks) < eff:
        nxt = min(cur + timedelta(seconds=cs), end)
        chunks.append((cur, nxt))
        cur = nxt
    planned_end = chunks[-1][1] if chunks else start
    return {"chunks": chunks, "required_chunks": required,
            "span_cap_chunks": span_cap, "eff_chunks": eff,
            "planned_end": planned_end, "truncated": planned_end < end}
