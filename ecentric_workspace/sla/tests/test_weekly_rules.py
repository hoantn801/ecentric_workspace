# Copyright (c) 2026, eCentric and contributors
"""Test luat doc `Weekly Team Update` - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_weekly_rules -v
"""
import unittest

from ecentric_workspace.sla.domain import weekly_rules as wr

D_DUE = "2026-09-12 17:00:00"
D_SUB = "2026-09-12 16:30:00"
D_MOD = "2026-09-13 08:00:00"


def _row(**kw):
    base = {"name": "WTU-001", "submitter": "a@ec.vn", "due_at": D_DUE,
            "status": "Draft", "submitted_at": None, "modified": D_MOD}
    base.update(kw)
    return base


class TestDecide(unittest.TestCase):
    def test_draft_opens(self):
        act, closed, _ = wr.decide(_row())
        self.assertEqual(act, wr.ACT_OPEN)
        self.assertIsNone(closed)

    def test_submitted_closes_at_submitted_at(self):
        act, closed, _ = wr.decide(_row(status="Submitted", submitted_at=D_SUB))
        self.assertEqual((act, closed), (wr.ACT_CLOSE, D_SUB))

    def test_reviewed_also_closes(self):
        act, _, _ = wr.decide(_row(status="Reviewed", submitted_at=D_SUB))
        self.assertEqual(act, wr.ACT_CLOSE)

    def test_submitted_without_timestamp_falls_back_to_modified(self):
        # Ban nop truoc khi truong `submitted_at` ton tai. Bo qua ca ban ghi thi
        # nguoi da nop bien mat khoi mau so - duoc mien phi.
        act, closed, _ = wr.decide(_row(status="Submitted", submitted_at=None))
        self.assertEqual((act, closed), (wr.ACT_CLOSE, D_MOD))

    def test_no_due_is_skipped_with_a_reason(self):
        act, _, reason = wr.decide(_row(due_at=None))
        self.assertEqual(act, wr.ACT_SKIP)
        self.assertIn("han", reason)

    def test_no_submitter_is_skipped_with_a_reason(self):
        act, _, reason = wr.decide(_row(submitter=None))
        self.assertEqual(act, wr.ACT_SKIP)
        self.assertIn("nguoi nop", reason)

    def test_missing_due_wins_over_terminal_status(self):
        # Da nop nhung khong co han -> van khong cham diem duoc. Dong mot nghia
        # vu khong co han se cham `Met` mien phi (xem scoring.classify_close).
        act, _, _ = wr.decide(_row(status="Submitted", submitted_at=D_SUB, due_at=None))
        self.assertEqual(act, wr.ACT_SKIP)

    def test_unknown_status_is_treated_as_still_open(self):
        # Khong doan. Mot trang thai la se KHONG duoc coi la da nop - sai huong
        # nay tao ra mot khieu nai; sai huong kia tao ra mot nguoi khong bi do.
        act, _, _ = wr.decide(_row(status="Cho duyet"))
        self.assertEqual(act, wr.ACT_OPEN)

    def test_empty_status_opens(self):
        act, _, _ = wr.decide(_row(status=None))
        self.assertEqual(act, wr.ACT_OPEN)


if __name__ == "__main__":
    unittest.main()
