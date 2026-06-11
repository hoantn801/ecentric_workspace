"""TZ-FIX 2026-06-10 tests - site-tz-aware epoch conversion for Omisell
order/list windows (root cause: drift_seconds = -25200, server UTC vs site
Asia/Ho_Chi_Minh; see 46_OMISELL_LIST_DIAGNOSTIC.md).

Part 1 (pure, runs anywhere): services.time_windows.epoch_in_tz/utc_str -
frappe-free by design, so correctness is provable independent of the server
timezone these tests happen to run on.

Part 2 (source-text, runs anywhere): asserts on the api_omisell.py SOURCE
(no import - module needs frappe) that the fix is wired in and the protected
logic (pull_one_order, monotonic checkpoint, overlap, chunking) is untouched.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_tz_epoch
"""
import calendar
import os
import unittest
from datetime import datetime, timedelta, timezone

from ecentric_workspace.alerts.services.time_windows import (
    DEFAULT_SITE_TZ, epoch_in_tz, utc_str)

VN = "Asia/Ho_Chi_Minh"
# Known target order (FES-VN): site wall time and its true UTC equivalent.
TARGET_SITE = datetime(2026, 6, 9, 21, 37, 39)
TARGET_UTC = datetime(2026, 6, 9, 14, 37, 39)          # 21:37:39 - 7h
TARGET_EPOCH = calendar.timegm(TARGET_UTC.timetuple())  # tz-independent truth


class TestEpochInTz(unittest.TestCase):
    def test_target_order_site_to_utc_epoch(self):
        """REQUIREMENT 5a: 2026-06-09 21:37:39 Asia/Ho_Chi_Minh ->
        epoch of 2026-06-09 14:37:39 UTC."""
        self.assertEqual(epoch_in_tz(TARGET_SITE, VN), TARGET_EPOCH)
        self.assertEqual(utc_str(TARGET_EPOCH), "2026-06-09 14:37:39")

    def test_default_tz_is_vn(self):
        self.assertEqual(DEFAULT_SITE_TZ, VN)
        self.assertEqual(epoch_in_tz(TARGET_SITE), TARGET_EPOCH)

    def test_independent_of_server_tz(self):
        """The old bug: int(naive.timestamp()) differs per server tz. The new
        conversion must NOT - same naive input in VN vs UTC differs by
        exactly 7h, regardless of where this test runs."""
        self.assertEqual(epoch_in_tz(TARGET_SITE, "UTC") - TARGET_EPOCH, 7 * 3600)

    def test_aware_datetime_passthrough(self):
        aware = TARGET_UTC.replace(tzinfo=timezone.utc)
        self.assertEqual(epoch_in_tz(aware, VN), TARGET_EPOCH)

    def test_non_datetime_raises(self):
        with self.assertRaises(TypeError):
            epoch_in_tz("2026-06-09 21:37:39", VN)

    def test_overlap_window_covers_target(self):
        """REQUIREMENT 5c: the failing scheduler window (site 2026-06-09
        19:16 -> 2026-06-10 01:18), converted CORRECTLY, contains the target
        order's true epoch - so the same overlap now catches it."""
        f = epoch_in_tz(datetime(2026, 6, 9, 19, 16, 0), VN)
        t = epoch_in_tz(datetime(2026, 6, 10, 1, 18, 0), VN)
        self.assertTrue(f <= TARGET_EPOCH <= t)
        self.assertEqual(utc_str(f), "2026-06-09 12:16:00")
        self.assertEqual(utc_str(t), "2026-06-09 18:18:00")

    def test_old_conversion_missed_target_when_server_utc(self):
        """Documents the bug: the SAME window converted the OLD way on a UTC
        server (naive treated as UTC) excludes the target."""
        f_old = calendar.timegm(datetime(2026, 6, 9, 19, 16, 0).timetuple())
        t_old = calendar.timegm(datetime(2026, 6, 10, 1, 18, 0).timetuple())
        self.assertFalse(f_old <= TARGET_EPOCH <= t_old)

    def test_monotonic_no_rollback_semantics(self):
        """REQUIREMENT 5b (pure model): replaying the checkpoint guard
        expression - prev if (prev and prev > t) else t - over an overlap
        re-scan never moves the checkpoint backward."""
        prev = datetime(2026, 6, 10, 1, 18, 0)
        for end in (prev - timedelta(hours=6),   # overlap chunk fully in past
                    prev - timedelta(minutes=1),
                    prev,                         # boundary: prev > t is False
                    prev + timedelta(minutes=15)):
            new = prev if (prev and prev > end) else end
            self.assertGreaterEqual(new, prev)


class TestApiOmisellSourceWiring(unittest.TestCase):
    """Assert against source text (api_omisell imports frappe -> no import)."""

    @property
    def src(self):
        path = os.path.join(os.path.dirname(__file__), "..", "api_omisell.py")
        with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
            return fh.read()

    def test_no_live_naive_timestamp_calls(self):
        """Every int(<var>.timestamp()) call site is gone (the docstring
        mention of int(naive.timestamp()) is allowed)."""
        import re
        pat = re.compile(r"int\((?:f|t|start|end)\.timestamp\(\)\)")
        hits = [line.strip() for line in self.src.splitlines()
                if pat.search(line.split("#", 1)[0])]  # ignore comments
        self.assertEqual(hits, [])

    def test_to_epoch_wired_into_list_calls(self):
        self.assertIn("def _to_epoch(dt):", self.src)
        self.assertIn("f_ts, t_ts = _to_epoch(f), _to_epoch(t)", self.src)
        self.assertIn("s_ts, e_ts = _to_epoch(start), _to_epoch(end)", self.src)
        self.assertIn(
            "from ecentric_workspace.alerts.services.time_windows import", self.src)

    def test_pull_one_order_unchanged(self):
        """REQUIREMENT 2: pull_one_order has no list/window/epoch logic."""
        body = self.src.split("def pull_one_order")[1].split("\ndef ")[0]
        for banned in ("get_orders", "_to_epoch", "updated_from", "epoch"):
            self.assertNotIn(banned, body)

    def test_checkpoint_guard_and_overlap_intact(self):
        """REQUIREMENT 3: monotonic checkpoint + overlap + chunking kept."""
        self.assertIn("prev if (prev and prev > t) else t", self.src)
        self.assertIn("def _overlap_minutes():", self.src)
        self.assertIn("requested_from - timedelta(minutes=overlap)", self.src)
        self.assertIn("chunk_windows(start, end, chunk_seconds=cs, max_chunks=eff_chunks)", self.src)
        self.assertIn("MAX_OVERLAP_CHUNKS = 12", self.src)

    def test_diagnostic_fields_in_run_summary(self):
        """REQUIREMENT 4: pull_status (via last_run) exposes the window
        diagnostics."""
        for field in ('"requested_from"', '"effective_from_after_overlap"',
                      '"epoch_from"', '"epoch_to"', '"utc_from"', '"utc_to"',
                      '"overlap_minutes"', '"epoch_window"', '"utc_window"'):
            self.assertIn(field, self.src)

    def test_no_new_write_surface(self):
        """Constraints: no Omisell write (client untouched - GET only), no
        stock write, no alert-engine change. The only .save sites remain the
        pre-existing BIS checkpoint/breaker/auth ones."""
        self.assertEqual(self.src.count(".save(ignore_permissions=True)"), 5)
        self.assertNotIn("stock", self.src.lower())


if __name__ == "__main__":
    unittest.main()
