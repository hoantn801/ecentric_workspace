# Copyright (c) 2026, eCentric and contributors
"""Quay so tuan - khong can bench.

    python -m unittest ecentric_workspace.dao_tao.tests.test_draw
"""
import datetime
import random
import unittest

from ecentric_workspace.dao_tao.tests import test_services  # noqa: F401  (cai frappe gia)
from ecentric_workspace.dao_tao.application import draw_service, ticket_service
from ecentric_workspace.dao_tao.application.access import Ctx
from ecentric_workspace.dao_tao.domain import draw as DR
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError, QuizPermissionError
from ecentric_workspace.dao_tao.tests.fake_repo import FakeRepo

HOST = Ctx("host@x", ["EC Training Host"])
A, B, C3 = Ctx("a@x", []), Ctx("b@x", []), Ctx("c@x", [])


class DrawTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo(now=datetime.datetime(2026, 11, 10, 9, 0))      # thu Ba
        ticket_service.grant(self.repo, A.user, "manual", "a", 3, "x")
        ticket_service.grant(self.repo, B.user, "manual", "b", 1, "x")

    def test_default_week_draw(self):
        v = draw_service.hub(A, self.repo)
        self.assertEqual(v["draw_at"], "2026-11-13 16:00:00")
        self.assertEqual((v["tickets"], v["open"], v["range"]), (3, True, 100))

    def test_pick_rules(self):
        draw_service.pick(A, self.repo, 7)
        with self.assertRaises(QuizError):
            draw_service.pick(B, self.repo, 7)                    # trung so
        with self.assertRaises(QuizError):
            draw_service.pick(B, self.repo, 101)                  # ngoai dai
        draw_service.pick(B, self.repo, 8)
        with self.assertRaises(QuizError):
            draw_service.pick(B, self.repo, 9)                    # B chi co 1 ve
        with self.assertRaises(QuizError):
            draw_service.pick(C3, self.repo, 9)                   # khong co ve
        v = draw_service.pick(A, self.repo, None, rng=random.Random(1))
        self.assertEqual(len(v["mine"]), 2)
        v = draw_service.release(A, self.repo, 7)
        self.assertEqual([m["number"] for m in v["mine"]], [m["number"] for m in v["mine"] if m["number"] != 7])
        self.repo.clock = datetime.datetime(2026, 11, 13, 15, 56)
        with self.assertRaises(QuizError):
            draw_service.pick(A, self.repo, 50)                   # da khoa 5 phut truoc

    def test_run_each_ticket_one_entry_and_unheld_prize_stays(self):
        draw_service.admin_save(HOST, self.repo, {"range": 10, "prizes": [{"label": "Trà sữa", "quantity": 8}]})
        draw_service.pick(A, self.repo, 1)
        self.repo.clock = datetime.datetime(2026, 11, 13, 16, 0, 30)
        draw_service.tick(self.repo)
        d = self.repo.get_draw(draw_service.current(self.repo)["name"])
        self.assertEqual(d["status"], "Done")
        nums = self.repo.draw_numbers(d["name"])
        self.assertEqual(len(nums), 4)                            # 3 ve A + 1 ve B -> 4 so (3 may chon)
        self.assertEqual(sum(1 for n in nums if n["auto"]), 3)
        self.assertEqual(len(d["results"]), 8)
        self.assertEqual(len({r["number"] for r in d["results"]}), 8)   # khong lap
        won = [r for r in d["results"] if r["user"]]
        self.assertLessEqual(len(won), 4)
        self.assertTrue(any(r["user"] is None for r in d["results"]))   # 8 qua / 10 so / 4 nguoi giu
        self.assertEqual(draw_service.tick(self.repo)["drawn"], 0)      # chay lai khong quay lai
        v = draw_service.hub(A, self.repo)
        self.assertEqual(len(v["results"]), 8)

    def test_admin_rules(self):
        with self.assertRaises(QuizPermissionError):
            draw_service.admin_save(A, self.repo, {"range": 50})
        with self.assertRaises(FieldErrors):
            draw_service.admin_save(HOST, self.repo, {"range": 5})
        with self.assertRaises(FieldErrors):
            draw_service.admin_save(HOST, self.repo, {"range": 50, "prizes": [{"label": "", "quantity": 2}]})
        draw_service.pick(A, self.repo, 60)
        with self.assertRaises(QuizError):
            draw_service.admin_save(HOST, self.repo, {"range": 50})       # da co nguoi giu so 60
        v = draw_service.admin_save(HOST, self.repo, {"range": 100, "draw_at": "2026-11-14T10:00",
                                                       "prizes": [{"label": "Áo", "quantity": 2}]})
        self.assertEqual(v["draw_at"], "2026-11-14 10:00:00")
        v = draw_service.draw_now(HOST, self.repo)
        self.assertEqual(v["status"], "Done")
        with self.assertRaises(QuizError):
            draw_service.draw_now(HOST, self.repo)

    def test_revoked_ticket_drops_extra_number(self):
        draw_service.pick(B, self.repo, 5)
        self.repo.revoke_ticket("manual", "b", B.user, "host@x")
        draw_service.admin_save(HOST, self.repo, {"range": 10, "prizes": [{"label": "X", "quantity": 10}]})
        res = draw_service.draw_now(HOST, self.repo)["results"]
        # Ve cua B da thu hoi -> so 5 khong con la cua B (may co the cap so 5 cho ve cua A).
        self.assertFalse(any(r["winner"] == B.user for r in res))

    def test_lucky_draw_small_first(self):
        prizes = [{"id": "p1", "label": "Lớn", "quantity": 1}, {"id": "p2", "label": "Nhỏ", "quantity": 2}]
        r = DR.lucky_draw(prizes, {}, 10, random.Random(2))
        self.assertEqual([x["prize"] for x in r], ["p2", "p2", "p1"])


if __name__ == "__main__":
    unittest.main()
