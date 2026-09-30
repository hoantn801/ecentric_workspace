# Copyright (c) 2026, eCentric and contributors
"""Phe duyet thang 9/2026 van do nhung KHONG vao %SLA; thang 10 tinh lai."""
import io
import os
import unittest

from ecentric_workspace.sla.constants import GROUP_APPROVAL, GROUP_ATTENDANCE, GROUP_TASK
from ecentric_workspace.sla.domain import scoring

HERE = os.path.dirname(os.path.abspath(__file__))
SLA = os.path.join(HERE, "..")


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def _bucket(late=0, missed=0, scored=1):
    return {"late": late, "missed": missed, "scored": scored, "rate": 50.0}


class TestCountsInPeriod(unittest.TestCase):
    def test_approval_thang_9_khong_tinh(self):
        self.assertEqual(scoring.counts_in_period(GROUP_APPROVAL, "2026-09"), 0)

    def test_approval_thang_10_tinh_lai(self):
        self.assertEqual(scoring.counts_in_period(GROUP_APPROVAL, "2026-10"), 1)

    def test_cham_cong_thang_9_van_tinh(self):
        self.assertEqual(scoring.counts_in_period(GROUP_ATTENDANCE, "2026-09"), 1)

    def test_task_van_khong_tinh(self):
        self.assertEqual(scoring.counts_in_period(GROUP_TASK, "2026-10"), 0)

    def test_khong_co_ky_doc_hang_so(self):
        self.assertEqual(scoring.counts_in_period(GROUP_APPROVAL), 1)


class TestContribution(unittest.TestCase):
    def test_thang_9_bo_approval(self):
        g = {GROUP_APPROVAL: _bucket(late=3), GROUP_ATTENDANCE: _bucket(missed=1)}
        keys = [r["group_key"] for r in scoring.contribution(g, "2026-09")]
        self.assertEqual(keys, [GROUP_ATTENDANCE])

    def test_thang_10_co_approval(self):
        g = {GROUP_APPROVAL: _bucket(late=3), GROUP_ATTENDANCE: _bucket(missed=1)}
        keys = [r["group_key"] for r in scoring.contribution(g, "2026-10")]
        self.assertEqual(keys, [GROUP_APPROVAL, GROUP_ATTENDANCE])

    def test_aggregate_doc_co_tung_dong(self):
        rows = [{"group_key": GROUP_APPROVAL, "counts_toward_sla": 0, "status": "Missed",
                 "due_at": "2026-09-10 10:00:00"},
                {"group_key": GROUP_ATTENDANCE, "counts_toward_sla": 1, "status": "Met",
                 "due_at": "2026-09-10 10:00:00", "closed_at": "2026-09-10 09:00:00"}]
        agg = scoring.aggregate(rows)
        self.assertEqual(agg["overall"]["rate"], 100.0)
        self.assertEqual(agg["groups"][GROUP_APPROVAL]["missed"], 1)


class TestNoiDay(unittest.TestCase):
    def test_open_obligation_ha_co_theo_ky(self):
        src = _read(SLA, "application", "obligation_service.py")
        self.assertIn("scoring.counts_in_period(t[\"group_key\"], due_rules.period_of(opened_at))", src)

    def test_bang_diem_truyen_ky(self):
        src = _read(SLA, "application", "scoreboard_service.py")
        self.assertIn('_decorate_groups(agg["groups"], period)', src)
        self.assertIn('scoring.contribution(agg["groups"], period)', src)

    def test_patch_dang_ky_va_khong_xoa(self):
        self.assertIn("ecentric_workspace.sla.patches.p016_approval_thang9_ngoai_sla",
                      _read(SLA, "..", "patches.txt"))
        src = _read(SLA, "patches", "p016_approval_thang9_ngoai_sla.py")
        for bad in ("delete", "DELETE", "\"status\""):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
