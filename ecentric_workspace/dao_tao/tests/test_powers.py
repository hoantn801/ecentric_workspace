# Copyright (c) 2026, eCentric and contributors
"""Power-up moi 5 cau - khong can bench.

    python -m unittest ecentric_workspace.dao_tao.tests.test_powers
"""
import random
import unittest

from ecentric_workspace.dao_tao.tests import test_services as T  # noqa: F401  (cai frappe gia)
from ecentric_workspace.dao_tao.application import play_service, room_service
from ecentric_workspace.dao_tao.domain import powers as PW
from ecentric_workspace.dao_tao.domain.errors import QuizError
from ecentric_workspace.dao_tao.tests.fake_repo import FakeRepo

HOST, STAFF = T.HOST, T.STAFF
QS = [{"type": "single", "text": "Câu %d" % i, "time": 20, "options": [{"text": "A"}, {"text": "B"}, {"text": "C"}, {"text": "D"}],
       "correct": [0]} for i in range(8)]
FLAT = {"by_speed": False, "streak": False, "last_double": False, "power_ups": True}


class PowersDomainTest(unittest.TestCase):
    def test_offer_and_catalog(self):
        self.assertEqual(len(PW.IDS), 12)
        o = PW.offer("seed-1")
        self.assertEqual(len(set(o)), 3)
        self.assertEqual(o, PW.offer("seed-1"))
        self.assertTrue(PW.offer_at(4, 21) and PW.offer_at(19, 21) and not PW.offer_at(20, 21) and not PW.offer_at(4, 5))

    def test_adjust(self):
        ok = {"points": 1000, "correct": True, "streak": 3, "bonus": 0}
        bad = {"points": 0, "correct": False, "streak": 0, "bonus": 0}
        self.assertEqual(PW.adjust(["double"], ok, 1.0, 2, "single")["points"], 2000)
        self.assertEqual(PW.adjust(["gamble"], ok, 1.0, 2, "single")["points"], 3000)
        self.assertEqual(PW.adjust(["gamble"], bad, 0.0, 2, "single")["points"], -200)
        self.assertEqual(PW.adjust(["insure"], bad, 0.0, 2, "single")["points"], 500)
        self.assertEqual(PW.adjust(["shield"], bad, 0.0, 2, "single")["streak"], 2)
        self.assertEqual(PW.adjust(["streak2"], ok, 1.0, 2, "single")["streak"], 5)
        self.assertEqual(PW.adjust(["boost5", "x15"], ok, 1.0, 2, "single")["points"], 1650)
        self.assertEqual(PW.adjust(["eliminate"], ok, 1.0, 2, "slider")["points"], 1150)
        self.assertEqual(PW.adjust(["double"], {"points": 0, "correct": None, "streak": 2}, None, 2, "poll")["points"], 0)
        self.assertEqual(PW.elapsed_for_score(["time"], 2000), 0)

    def test_activate_consume(self):
        st = PW.clean_state({"bag": ["boost5", "double"]})
        st = PW.activate(st, "boost5", 6)
        self.assertEqual(st["bag"], ["double"])
        self.assertEqual(PW.effective(st, 5), [])
        self.assertEqual(PW.effective(st, 6), ["boost5"])
        for i in range(6, 11):
            st = PW.consume(st, i)
        self.assertEqual(st["active"], [])
        self.assertIn("boost5", st["used"])


class StealDomainTest(unittest.TestCase):
    def rows(self, *scores, guard=()):
        return [{"user": "u%d" % i, "score": sc, "rank": i + 1, "nickname": "N%d" % i,
                 "powers": {"bag": ["guard"]} if i in guard else {}} for i, sc in enumerate(scores)]

    def test_steal_cases(self):
        ch, ev = PW.apply_steals(self.rows(1000, 800, 500), ["u2"], lambda u: 200)
        self.assertEqual((ch["u1"]["score"], ch["u2"]["score"]), (600, 700))
        self.assertEqual((ev[0]["victim_nick"], ev[0]["amount"], ev[0]["blocked"]), ("N1", 200, False))
        ch, ev = PW.apply_steals(self.rows(1000, 800, guard=(0,)), ["u1"], lambda u: 300)
        self.assertTrue(ev[0]["blocked"])
        self.assertEqual(ch["u0"]["powers"]["bag"], [])
        self.assertNotIn("score", ch.get("u1", {}))
        ch, ev = PW.apply_steals(self.rows(1000, 50), ["u0"], lambda u: 300)   # hang 1 lay cua hang 2, khong am
        self.assertEqual((ch["u1"]["score"], ch["u0"]["score"], ev[0]["amount"]), (0, 1050, 50))
        ch, ev = PW.apply_steals(self.rows(1000, 800, 700), ["u1", "u2"], lambda u: 300)
        self.assertEqual([e["thief"] for e in ev], ["u1", "u2"])              # tuan tu theo hang
        self.assertEqual(PW.apply_steals(self.rows(500), ["u0"], lambda u: 100), ({}, []))
        self.assertIn(PW.steal_amount("x"), PW.STEAL_AMOUNTS)


class PowersFlowTest(unittest.TestCase):
    def setUp(self, settings=FLAT):
        self.repo = FakeRepo()
        qid = T.build_quiz(self.repo, qs=QS, settings=dict(settings))
        r = room_service.open_room(HOST, self.repo, qid, rng=random.Random(3))
        self.code, self.sess = r["code"], r["session"]
        for c in STAFF[:2]:
            play_service.join(c, self.repo, self.code, device="d-" + c.user)

    def act(self, action):
        s = self.repo.get_session(self.sess)
        if action == "reveal" and s["phase"] == "reveal":
            return
        room_service.act(HOST, self.repo, self.sess, action, s["version"])

    def q(self):
        s = self.repo.get_session(self.sess)
        return s["questions"][s["index"]]

    def ans(self, ctx, right=True):
        self.repo.tick(3500)
        q = self.q()
        o = q["correct"][0] if right else [x["id"] for x in q["options"] if x["id"] not in q["correct"]][0]
        play_service.answer(ctx, self.repo, self.code, q["id"], {"o": o}, device="d-" + ctx.user)

    def state(self, ctx):
        return play_service.state(ctx, self.repo, self.code, "d-" + ctx.user)

    def play_to_offer(self):
        self.act("start")
        for i in range(5):
            if i:
                self.act("next")
            for c in STAFF[:2]:
                self.ans(c)
        self.assertEqual(self.repo.get_session(self.sess)["phase"], "reveal")

    def score(self, ctx):
        return self.repo.get_player(self.sess, ctx.user)["score"]

    def test_offer_pick_and_double(self):
        self.act("start")
        self.assertIsNone(self.state(STAFF[0])["power"]["offer"])
        for c in STAFF[:2]:
            self.ans(c)
        self.assertIsNone(self.state(STAFF[0])["power"]["offer"])     # chua toi cau 5
        self.repo.update_player(self.sess, STAFF[0].user, {})
        for i in range(1, 5):
            self.act("next")
            for c in STAFF[:2]:
                self.ans(c)
        st = self.state(STAFF[0])
        offer = [o["id"] for o in st["power"]["offer"]]
        self.assertEqual(len(offer), 3)
        not_offered = [i for i in PW.IDS if i not in offer][0]
        with self.assertRaises(QuizError):
            play_service.pick_power(STAFF[0], self.repo, self.code, not_offered, "d-" + STAFF[0].user)
        play_service.pick_power(STAFF[1], self.repo, self.code, "skip", "d-" + STAFF[1].user)
        self.assertEqual(self.state(STAFF[1])["power"]["picked"]["id"], "skip")
        with self.assertRaises(QuizError):
            play_service.pick_power(STAFF[1], self.repo, self.code, offer[0], "d-" + STAFF[1].user)
        # Dat thang "double" vao tui de kiem diem
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {"bag": ["double"], "picked": {"4": "double"}}})
        self.act("next")
        before = self.score(STAFF[0])
        with self.assertRaises(QuizError):
            play_service.use_power(STAFF[0], self.repo, self.code, "gamble", "d-" + STAFF[0].user)
        play_service.use_power(STAFF[0], self.repo, self.code, "double", "d-" + STAFF[0].user)
        self.assertEqual(self.state(STAFF[0])["power"]["bag"], [])
        for c in STAFF[:2]:
            self.ans(c)
        self.assertEqual(self.score(STAFF[0]) - before, 2000)
        self.assertEqual(self.repo.get_player(self.sess, STAFF[0].user)["powers"]["active"], [])

    def test_gold_eliminate_gamble(self):
        self.play_to_offer()
        before = self.score(STAFF[0])
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {}})
        # gold co trong offer? ep vao bang cach doi seed khong duoc -> kiem truc tiep qua tui
        offer = [o["id"] for o in self.state(STAFF[0])["power"]["offer"]]
        pick = "gold" if "gold" in offer else offer[0]
        play_service.pick_power(STAFF[0], self.repo, self.code, pick, "d-" + STAFF[0].user)
        if pick == "gold":
            self.assertEqual(self.score(STAFF[0]) - before, 300)
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {"bag": ["eliminate", "gamble"], "picked": {"4": pick}}})
        self.act("next")
        play_service.use_power(STAFF[0], self.repo, self.code, "eliminate", "d-" + STAFF[0].user)
        n0 = [o for o in self.state(STAFF[0])["question"]["options"] if not o.get("gone")]
        n1 = [o for o in self.state(STAFF[1])["question"]["options"] if not o.get("gone")]
        self.assertEqual((len(n0), len(n1)), (3, 4))
        self.assertIn(self.q()["correct"][0], [o["id"] for o in n0])
        play_service.use_power(STAFF[0], self.repo, self.code, "gamble", "d-" + STAFF[0].user)
        self.repo.update_player(self.sess, STAFF[0].user, {"score": 100})
        self.ans(STAFF[0], right=False)
        self.ans(STAFF[1])
        self.assertEqual(self.score(STAFF[0]), 0)                       # 100 - 200 -> san 0
        with self.assertRaises(QuizError):                              # het tui
            play_service.use_power(STAFF[0], self.repo, self.code, "gamble", "d-" + STAFF[0].user)

    def test_insure_blank_and_off(self):
        self.play_to_offer()
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {"bag": ["insure"], "picked": {"4": "insure"}}})
        self.act("next")
        play_service.use_power(STAFF[0], self.repo, self.code, "insure", "d-" + STAFF[0].user)
        before = self.score(STAFF[0])
        self.ans(STAFF[1])
        self.repo.tick(30000)
        self.state(STAFF[1])                                            # het gio -> khoa + cong bo
        self.assertEqual(self.score(STAFF[0]) - before, 500)

    def test_steal_flow(self):
        self.play_to_offer()
        self.repo.update_player(self.sess, STAFF[0].user, {"score": 3000, "powers": {"picked": {"4": "steal"}}})
        self.repo.update_player(self.sess, STAFF[1].user, {"score": 5000, "powers": {"bag": ["guard"], "picked": {"4": "guard"}}})
        self.act("next")
        with self.assertRaises(QuizError):
            play_service.use_power(STAFF[1], self.repo, self.code, "guard", "d-" + STAFF[1].user)
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {"bag": ["steal"], "picked": {"4": "steal"}}})
        play_service.use_power(STAFF[0], self.repo, self.code, "steal", "d-" + STAFF[0].user)
        for c in STAFF[:2]:
            self.ans(c)
        host = room_service.host_state(HOST, self.repo, self.sess)
        self.assertTrue(host["steals"][0]["blocked"])
        self.assertEqual(self.score(STAFF[1]), 6000)
        self.assertEqual(self.state(STAFF[1])["steals"][0]["role"], "victim")
        # lan 2: het khien -> mat diem, bang xep hang da tinh lai
        self.act("next")
        self.repo.update_player(self.sess, STAFF[0].user, {"powers": {"bag": ["steal"], "picked": {"4": "steal"}}})
        play_service.use_power(STAFF[0], self.repo, self.code, "steal", "d-" + STAFF[0].user)
        for c in STAFF[:2]:
            self.ans(c)
        ev = room_service.host_state(HOST, self.repo, self.sess)["steals"][0]
        self.assertFalse(ev["blocked"])
        self.assertEqual(self.score(STAFF[1]), 7000 - ev["amount"])
        self.assertEqual(self.score(STAFF[0]), 5000 + ev["amount"])
        board = {r["email"]: r["score"] for r in self.repo.get_session(self.sess)["state"]["board"]}
        self.assertEqual(board[STAFF[0].user], 5000 + ev["amount"])
        me = self.state(STAFF[0])["steals"][0]
        self.assertEqual((me["role"], me["amount"]), ("thief", ev["amount"]))

    def test_setting_off(self):
        self.setUp(settings=dict(FLAT, power_ups=False))
        self.play_to_offer()
        self.assertNotIn("power", self.state(STAFF[0]))
        self.assertNotIn("steals", room_service.host_state(HOST, self.repo, self.sess))
        with self.assertRaises(QuizError):
            play_service.pick_power(STAFF[0], self.repo, self.code, "skip", "d-" + STAFF[0].user)


if __name__ == "__main__":
    unittest.main()
