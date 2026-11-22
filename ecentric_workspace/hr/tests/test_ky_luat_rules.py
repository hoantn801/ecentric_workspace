# Copyright (c) 2026, eCentric and contributors
"""Ky luat - luat chon the / hinh thuc / can cu D125, tai pham, goi y the vang, chan xoa khi tai pham.

    python3 -m unittest ecentric_workspace.hr.tests.test_ky_luat_rules
"""
import datetime as dt
import unittest

from ecentric_workspace.hr.tests import ky_luat_fake  # noqa: F401
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.domain import rules as R

d = dt.date
TODAY = d(2026, 11, 23)


class TestChoice(unittest.TestCase):
    def v(self, prior=(), **kw):
        return R.validate_choice(dict(kw, today=TODAY), prior)

    def test_red_only_reprimand(self):
        self.assertEqual(self.v(card=C.CARD_RED, penalty=C.P_REPRIMAND), {})
        self.assertIn("penalty", self.v(card=C.CARD_RED, penalty=C.P_DISMISS))

    def test_black_requires_sub_penalty(self):
        self.assertIn("penalty", self.v(card=C.CARD_BLACK, penalty=""))
        self.assertIn("penalty", self.v(card=C.CARD_BLACK, penalty=C.P_REPRIMAND))

    def test_extend_months_1_to_6(self):
        self.assertIn("extend_months", self.v(card=C.CARD_BLACK, penalty=C.P_EXTEND, extend_months=7))
        self.assertIn("extend_months", self.v(card=C.CARD_BLACK, penalty=C.P_EXTEND, extend_months=0))
        self.assertEqual(self.v(card=C.CARD_BLACK, penalty=C.P_EXTEND, extend_months=6), {})

    def test_demote_requires_position(self):
        self.assertIn("holds_position", self.v(card=C.CARD_BLACK, penalty=C.P_DEMOTE))
        self.assertEqual(self.v(card=C.CARD_BLACK, penalty=C.P_DEMOTE, holds_position=1), {})

    def test_dismiss_requires_ground(self):
        self.assertIn("dismissal_ground", self.v(card=C.CARD_BLACK, penalty=C.P_DISMISS))
        self.assertIn("dismissal_ground", self.v(card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="9"))
        self.assertEqual(self.v(card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="1"), {})

    def test_ground_3_needs_unexpunged_extend_or_demote(self):
        self.assertIn("dismissal_ground", self.v(card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="3"))
        prior_rep = [{"name": "A", "status": C.S_ISSUED, "penalty": C.P_REPRIMAND, "expunge_due": d(2027, 1, 1)}]
        self.assertIn("dismissal_ground", self.v(prior_rep, card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="3"))
        prior_old = [{"name": "B", "status": C.S_ISSUED, "penalty": C.P_EXTEND, "expunge_due": d(2026, 11, 1)}]
        self.assertIn("dismissal_ground", self.v(prior_old, card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="3"))
        prior_ok = [{"name": "C", "status": C.S_ISSUED, "penalty": C.P_EXTEND, "expunge_due": d(2027, 3, 1)}]
        self.assertEqual(self.v(prior_ok, card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="3"), {})
        prior_expunged = [{"name": "D", "status": C.S_EXPUNGED, "penalty": C.P_DEMOTE, "expunge_due": d(2027, 3, 1)}]
        self.assertIn("dismissal_ground", self.v(prior_expunged, card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="3"))

    def test_ground_only_with_dismissal(self):
        self.assertIn("dismissal_ground", self.v(card=C.CARD_RED, penalty=C.P_REPRIMAND, dismissal_ground="1"))


class TestRecidivism(unittest.TestCase):
    def test_note_lists_active(self):
        prior = [{"name": "K1", "status": C.S_ISSUED, "penalty": C.P_REPRIMAND, "decision_date": d(2026, 10, 1),
                  "expunge_due": d(2027, 1, 1)},
                 {"name": "K2", "status": C.S_ISSUED, "penalty": C.P_REPRIMAND, "decision_date": d(2026, 1, 1),
                  "expunge_due": d(2026, 4, 1)}]
        note = R.recidivism_note(prior, TODAY)
        self.assertIn("K1", note)
        self.assertNotIn("K2", note)
        self.assertEqual(R.recidivism_note([], TODAY), "")

    def test_dismissal_never_expires(self):
        prior = [{"name": "S", "status": C.S_ISSUED, "penalty": C.P_DISMISS, "expunge_due": None}]
        self.assertEqual(len(R.active_disciplines(prior, TODAY)), 1)


class TestYellowHint(unittest.TestCase):
    def test_three_in_90_days(self):
        self.assertTrue(R.yellow_hint([d(2026, 9, 1), d(2026, 10, 1), d(2026, 11, 20)], TODAY))
        self.assertEqual(R.yellow_hint([d(2026, 8, 1), d(2026, 10, 1), d(2026, 11, 20)], TODAY), "")
        self.assertEqual(R.yellow_hint([d(2026, 10, 1), d(2026, 11, 20)], TODAY), "")


class TestExpungeBlock(unittest.TestCase):
    def test_later_decision_inside_window_blocks(self):
        case = {"name": "K1", "decision_date": d(2026, 8, 1), "expunge_due": d(2026, 11, 1)}
        later = [{"name": "K2", "status": C.S_ISSUED, "decision_date": d(2026, 10, 1)},
                 {"name": "K3", "status": C.S_ISSUED, "decision_date": d(2026, 11, 2)},
                 {"name": "K4", "status": C.S_NO_DISCIPLINE, "decision_date": d(2026, 9, 1)}]
        self.assertEqual(R.expunge_blocked_by(case, later), ["K2"])


if __name__ == "__main__":
    unittest.main()
