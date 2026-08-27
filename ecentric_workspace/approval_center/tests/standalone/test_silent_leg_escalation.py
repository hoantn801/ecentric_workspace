# Copyright (c) 2026, eCentric and contributors
"""A leg the provider accepted and then ignored must surface in minutes, not a day.

2026-08-27, EC-DSR-2026-00012. eContract accepted the signing job, returned a transaction
id, and then did nothing: no signature, and not even a row in its own workflow log. The leg
sat in `Verifying` looking exactly like a leg that was merely slow. The only backstop was
`sweep_stale` at twenty-four hours.

Measured on this system, a leg the provider accepts produces a signature in 2s, 2s and 1s.
Twenty minutes of silence is therefore not slowness; it is a stuck job, and somebody has to
look at it. On a system carrying real payment approvals, a day of looking-busy-while-stuck
is not an acceptable failure mode.

The escalation is deliberately narrow: only legs already ACCEPTED by the provider, and it
moves them to Manual Review rather than retrying - re-sending a non-idempotent signing write
could produce a second signature.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s. Da thu:\n  %s" % (parts[-1], "\n  ".join(tried)))


def _fn(src, name):
    m = re.search(r"\ndef %s\(\):(.*?)(?=\ndef |\Z)" % name, src, re.S)
    assert m, "khong tim thay %s" % name
    return m.group(1)


class TestEscalation(unittest.TestCase):
    def setUp(self):
        self.tasks = _src("platform", "esign", "tasks.py")
        self.body = _fn(self.tasks, "flag_silent_legs")

    def test_threshold_is_minutes_not_hours(self):
        m = re.search(r"PROVIDER_SILENCE_MINUTES = (\d+)", self.tasks)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 60, "qua lau thi khong khac gi sweep_stale")
        self.assertGreaterEqual(int(m.group(1)), 10,
                                "qua ngan se bao dong nham khi nha cung cap cham that")

    def test_only_legs_the_provider_already_accepted(self):
        self.assertIn('"Provider Accepted", "Verifying"', self.body)
        for never in ("Queued", "Prepared", "Draft"):
            self.assertNotIn('"%s"' % never, self.body,
                             "chan chua roi khoi he minh thi khong phai loi nha cung cap: %s" % never)

    def test_it_escalates_and_never_retries(self):
        self.assertIn('"Manual Review"', self.body)
        for banned in ("approve_and_sign", "bulk_process", "transition_with_recipients",
                       "retry_signature_request"):
            self.assertNotIn(banned, self.body,
                             "gui lai mot lenh ky KHONG bat bien co the tao chu ky thu hai: %s" % banned)

    def test_the_reason_is_recorded_not_just_the_status(self):
        self.assertIn("provider_accepted_but_silent", self.body)
        self.assertIn("error_summary", self.body,
                      "doi trang thai ma khong noi vi sao thi nguoi truc khong biet lam gi")

    def test_it_measures_from_acceptance(self):
        self.assertIn("r.accepted_at", self.body,
                      "phai do tu luc nha cung cap NHAN lenh, khong phai luc sua cuoi")

    def test_it_creates_work_for_a_human(self):
        self.assertIn("_dead_letter_todo(r.name)", self.body)

    def test_one_bad_row_does_not_stop_the_sweep(self):
        self.assertIn("except Exception:", self.body)
        self.assertIn("frappe.log_error", self.body)

    def test_the_kill_switch_still_applies(self):
        self.assertIn("if _disabled():", self.body)


class TestItIsScheduled(unittest.TestCase):
    def test_registered_on_the_five_minute_cron(self):
        hooks = _src("hooks.py")
        block = re.search(r'"\*/5 \* \* \* \*":\s*\[(.*?)\]', hooks, re.S)
        self.assertIsNotNone(block)
        self.assertIn("tasks.flag_silent_legs", block.group(1),
                      "viet ham ma khong lich chay thi khong bao gio chay")

    def test_declared_exactly_once(self):
        self.assertEqual(_src("hooks.py").count("tasks.flag_silent_legs"), 1)


if __name__ == "__main__":
    unittest.main()
