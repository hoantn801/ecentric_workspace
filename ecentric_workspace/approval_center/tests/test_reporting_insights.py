# Copyright (c) 2026, eCentric and contributors
"""Rule-based insight tests (pure Python; runs under bench AND standalone)."""
import unittest

from ecentric_workspace.approval_center.reporting import insights as _ins


def _dash(**over):
    base = {"kpis": {}, "comparison": {}, "department_performance": [], "bottleneck_levels": [],
            "pending_by_approver": [], "longest_pending": []}
    base.update(over)
    return base


class TestInsights(unittest.TestCase):
    def _codes(self, dash):
        return [i["code"] for i in _ins.generate(dash)]

    def test_all_clear_when_nothing(self):
        self.assertEqual(self._codes(_dash()), ["all_clear"])

    def test_pending_swing_over_threshold(self):
        codes = self._codes(_dash(comparison={"pending": {"current": 30, "previous": 20, "pct": 50.0, "direction": "up"}}))
        self.assertIn("pending_swing", codes)

    def test_pending_swing_below_threshold_silent(self):
        codes = self._codes(_dash(comparison={"pending": {"current": 21, "previous": 20, "pct": 5.0, "direction": "up"}}))
        self.assertNotIn("pending_swing", codes)

    def test_top_breach_department_and_severity(self):
        res = _ins.generate(_dash(department_performance=[{"department": "Fin", "breaches": 5}]))
        hit = [i for i in res if i["code"] == "top_breach_department"][0]
        self.assertEqual(hit["severity"], "critical")   # >=3 -> critical
        self.assertEqual(hit["filter"]["department"], "Fin")

    def test_approver_high_load(self):
        self.assertIn("approver_high_load",
                      self._codes(_dash(pending_by_approver=[{"label": "x", "count": 12}])))

    def test_older_than_p90(self):
        codes = self._codes(_dash(bottleneck_levels=[{"level": "L", "p90_seconds": 100000}],
                                  longest_pending=[{"pending_age_seconds": 200000}]))
        self.assertIn("older_than_p90", codes)

    def test_completion_decline_and_avg_time(self):
        codes = self._codes(_dash(comparison={
            "completion_rate": {"current": 60, "previous": 75, "delta": -15},
            "avg_approval_seconds": {"current": 180000, "previous": 120000, "pct": 50.0}}))
        self.assertIn("completion_decline", codes)
        self.assertIn("avg_time_deterioration", codes)

    def test_every_insight_has_required_shape(self):
        res = _ins.generate(_dash(pending_by_approver=[{"label": "x", "count": 20}]))
        for i in res:
            self.assertIn(i["severity"], ("info", "warning", "critical"))
            self.assertTrue(i["statement"])
            self.assertIn("filter", i)


if __name__ == "__main__":
    unittest.main()
