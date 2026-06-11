"""Catch-up planner tests (fix 2026-06-12) - LOF stale-checkpoint incident.

REQ 7a: stale last_sync_at + 30m chunks must cover the full window to `to`.
REQ 7b: caught_up=false when the run cannot reach `to` (source-level).
REQ 7c: caught_up=true only when the final chunk end == to.
REQ 7d: monitor stops going stale because the span cap (12h) >> overlap (6h).

Planner is PURE (services/pull_planner.py) - runs anywhere.
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_catchup_planner
"""
import os
import unittest
from datetime import datetime, timedelta

from ecentric_workspace.alerts.services.pull_planner import plan

SPAN_12H = 12 * 3600

# The exact LOF-VN incident window:
LOF_FROM = datetime(2026, 6, 11, 14, 48, 52)   # last_sync 20:48:52 - 6h overlap
LOF_TO = datetime(2026, 6, 12, 1, 17, 45)      # now at run time


class TestIncidentWindow(unittest.TestCase):
    def test_lof_window_reaches_to_with_30m_chunks(self):
        """REQ 7a: 14:48->01:17 (~10.5h) at 1800s needs 21 chunks; the old
        fixed cap of 12 stopped at 20:48. Span cap 12h=24 chunks covers it."""
        p = plan(LOF_FROM, LOF_TO, 1800, 4, SPAN_12H)
        self.assertEqual(p["required_chunks"], 21)
        self.assertEqual(p["span_cap_chunks"], 24)
        self.assertEqual(p["eff_chunks"], 21)
        self.assertFalse(p["truncated"])
        self.assertEqual(p["planned_end"], LOF_TO)          # REQ 7c precondition
        self.assertEqual(p["chunks"][-1][1], LOF_TO)
        self.assertEqual(len(p["chunks"]), 21)

    def test_old_behavior_would_have_truncated(self):
        """Documents the bug: with the old count cap (12) the same plan stops
        at 6h - exactly the overlap - and never reaches `to`."""
        p = plan(LOF_FROM, LOF_TO, 1800, 4, 12 * 1800)  # old effective span 6h
        self.assertTrue(p["truncated"])
        self.assertEqual(p["planned_end"], LOF_FROM + timedelta(hours=6))
        self.assertLess(p["planned_end"], LOF_TO)


class TestPlannerRules(unittest.TestCase):
    def test_truncation_reported_beyond_span_cap(self):
        """REQ 7b: a 30h backlog at 30m chunks truncates at 12h and SAYS so."""
        start = datetime(2026, 6, 10, 0, 0, 0)
        end = start + timedelta(hours=30)
        p = plan(start, end, 1800, 4, SPAN_12H)
        self.assertTrue(p["truncated"])
        self.assertEqual(len(p["chunks"]), 24)
        self.assertEqual(p["planned_end"], start + timedelta(hours=12))

    def test_chunks_contiguous_and_bounded(self):
        p = plan(LOF_FROM, LOF_TO, 1800, 4, SPAN_12H)
        for i, (f, t) in enumerate(p["chunks"]):
            self.assertLessEqual((t - f).total_seconds(), 1800)
            if i:
                self.assertEqual(f, p["chunks"][i - 1][1])  # no gaps/overlap

    def test_one_hour_chunks_unchanged_behavior(self):
        """FES-VN path: 1h chunks, small window -> same plan as before."""
        start = datetime(2026, 6, 11, 0, 0, 0)
        end = start + timedelta(hours=6, minutes=30)
        p = plan(start, end, 3600, 4, SPAN_12H)
        self.assertEqual(p["required_chunks"], 7)
        self.assertEqual(len(p["chunks"]), 7)
        self.assertFalse(p["truncated"])

    def test_min_chunks_respected_but_not_past_end(self):
        start = datetime(2026, 6, 11, 0, 0, 0)
        p = plan(start, start + timedelta(minutes=10), 3600, 4, SPAN_12H)
        self.assertEqual(len(p["chunks"]), 1)  # window < 1 chunk
        self.assertFalse(p["truncated"])

    def test_empty_and_inverted_windows(self):
        t0 = datetime(2026, 6, 11, 0, 0, 0)
        for end in (t0, t0 - timedelta(hours=1), None):
            p = plan(t0, end, 1800, 4, SPAN_12H)
            self.assertEqual(p["chunks"], [])
            self.assertFalse(p["truncated"])


def _src():
    path = os.path.join(os.path.dirname(__file__), "..", "api_omisell.py")
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestJobWiring(unittest.TestCase):
    def test_caught_up_requires_reaching_to(self):
        """REQ 7b/7c: caught_up = all chunks done AND plan not truncated."""
        s = _src()
        self.assertIn('run["caught_up"] = bool(done_all and not p["truncated"])', s)
        self.assertNotIn('run["caught_up"] = run["chunks_done"] == len(chunks)', s)

    def test_done_partial_and_progress_fields(self):
        """REQ 4: partial runs are visible and resumable."""
        s = _src()
        self.assertIn('"done" if run["caught_up"] else "done_partial"', s)
        for field in ('"next_from"', '"remaining_seconds"', '"capped_at"',
                      '"required_chunks"', '"planned_to"'):
            self.assertIn(field, s)

    def test_span_constant_and_planner_wired(self):
        s = _src()
        self.assertIn("MAX_CATCHUP_SPAN_SECONDS = MAX_OVERLAP_CHUNKS * MAX_WINDOW_SECONDS", s)
        self.assertIn("pull_planner.plan(start, end, cs, int(max_chunks),", s)

    def test_checkpoint_monotonic_and_lock_finally_intact(self):
        """REQ 5 + 6: last_sync_at advances per successful chunk (monotonic
        guard) and the running lock is always cleared in finally."""
        s = _src()
        self.assertIn("prev if (prev and prev > t) else t", s)
        self.assertIn("last_end = ct", s)
        job = s.split("def pull_recent_job")[1]
        self.assertIn("cache.delete_value(_running_key(brand))",
                      job.split("finally:")[1])


if __name__ == "__main__":
    unittest.main()
