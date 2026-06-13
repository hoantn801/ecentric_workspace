"""Pure unit tests for the adaptive sub-window split math (scalability
mini-phase 2026-06-14). No frappe, no I/O - imports the real planner.

    bench run-tests --module ecentric_workspace.alerts.tests.test_subwindow_planner
"""
import unittest
from datetime import datetime, timedelta

from ecentric_workspace.alerts.services import subwindow_planner as swp

H0 = datetime(2026, 6, 14, 0, 0, 0)


def E(dt):
    return int(dt.timestamp())


class TestSubwindowPlanner(unittest.TestCase):
    def test_can_split_condition(self):
        # binding: split ONLY when width > min AND depth < max_depth
        self.assertTrue(swp.can_split(600, 0, 300, 6))
        self.assertFalse(swp.can_split(300, 0, 300, 6))   # width == min -> NO
        self.assertFalse(swp.can_split(600, 6, 300, 6))   # depth == max -> NO
        self.assertFalse(swp.can_split(299, 0, 300, 6))

    def test_split_point_whole_seconds_strictly_between(self):
        ct = H0 + timedelta(hours=1)
        mid = swp.split_point(H0, ct)
        self.assertEqual(mid, H0 + timedelta(seconds=1800))
        self.assertTrue(H0 < mid < ct)
        self.assertEqual((mid - H0).microseconds, 0)

    def test_shared_boundary_passthrough(self):
        # SHARED-BOUNDARY: api_upper_bound passes epoch(to) UNCHANGED (no +/-1).
        # Adjacent queries share the seam instant, so no second is skipped under
        # any (unknown) remote inclusivity; order_key dedupe absorbs the overlap.
        ct = H0 + timedelta(hours=1)
        mid = swp.split_point(H0, ct)
        left_hi = swp.api_upper_bound(E(mid))      # left  -> updated_to = E(mid)
        right_lo = E(mid)                          # right -> updated_from = E(mid)
        self.assertEqual(left_hi, E(mid))          # passthrough, NOT E(mid)-1
        self.assertEqual(left_hi, right_lo)        # adjacent queries SHARE the seam

    def test_stop_states_are_distinct(self):
        self.assertEqual(len(set(swp.STOP_STATES)), len(swp.STOP_STATES))
        self.assertEqual(swp.ADVANCEABLE_STATES, (swp.COMPLETED,))


if __name__ == "__main__":
    unittest.main()
