# -*- coding: utf-8 -*-
"""Timer Stop ghi Timesheet: khung gio phai KET THUC luc bam Stop, khong troi sang tuong lai.

Loi cu: from_time = PM Timer.start_time. Timer da Tam dung (start_time = None) -> from_time = luc
Stop, cong `hours` -> to_time nam o tuong lai. Timer Tam dung roi Tiep tuc -> start_time = luc
tiep tuc, cong ca phan da tich luy truoc do -> to_time cung troi sang tuong lai (va de gay loi
"overlap" voi lan ghi gio ke tiep cua chinh nguoi do). Fake frappe, no bench.
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class TestTimerStopWindow(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.doctypes.add("PM Timer")
        self.tm = self.fk.load("ecentric_workspace.pm.api.timer")
        self.tm.pmperm.require_pm_access = lambda *a, **k: None
        self.calls = []

        def fake_create(user, task, project, hours, description=None, from_time=None):
            self.calls.append({"hours": hours, "from_time": from_time})
            return "TS-1"
        self.tm.pmts._create_timesheet = fake_create
        self.fk.set_user(F.ALICE)

    def _timer(self, **kw):
        row = dict(name=F.ALICE, user=F.ALICE, task="T", project=None, accumulated_seconds=0,
                   status="Running", start_time=None)
        row.update(kw)
        self.fk.add("PM Timer", **row)

    def _window(self):
        c = self.calls[-1]
        start = self.fk.utils.get_datetime(c["from_time"])
        return start, start + datetime.timedelta(hours=c["hours"])

    def test_running_timer_keeps_real_start(self):
        now = self.fk._now
        self._timer(start_time=now - datetime.timedelta(hours=2))
        self.tm.stop()
        start, end = self._window()
        self.assertEqual(start, now - datetime.timedelta(hours=2))
        self.assertEqual(end, now)

    def test_paused_timer_does_not_end_in_future(self):
        now = self.fk._now
        self._timer(status="Paused", start_time=None, accumulated_seconds=3 * 3600)
        self.tm.stop()
        start, end = self._window()
        self.assertLessEqual(end, now)
        self.assertEqual(start, now - datetime.timedelta(hours=3))

    def test_resumed_timer_does_not_end_in_future(self):
        now = self.fk._now
        # 2h tich luy truoc khi tam dung + 1h ke tu luc tiep tuc = 3h
        self._timer(start_time=now - datetime.timedelta(hours=1), accumulated_seconds=2 * 3600)
        self.tm.stop()
        start, end = self._window()
        self.assertEqual(self.calls[-1]["hours"], 3.0)
        self.assertLessEqual(end, now)


if __name__ == "__main__":
    unittest.main()
