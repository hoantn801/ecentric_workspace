# Copyright (c) 2026, eCentric and contributors
"""Domain Dao tao / Quiz - khong can bench.

    python -m unittest ecentric_workspace.dao_tao.tests.test_domain
"""
import datetime
import itertools
import json
import random
import unittest

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain import (board, importer, lesson, prizes, profile,
                                               questions as Q, room, scoring, settings, tickets)
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError


def rid_seq():
    c = itertools.count(1)
    return lambda: "id%04d" % next(c)


def make(qs):
    return Q.require_valid(qs, rid_seq())


SAMPLE = [
    {"type": "single", "text": "Claude là gì?", "options": [{"text": "AI"}, {"text": "Bánh"}], "correct": [0]},
    {"type": "multi", "text": "Chọn 2", "options": [{"text": "A"}, {"text": "B"}, {"text": "C"}], "correct": [0, 2]},
    {"type": "truefalse", "text": "Đúng?", "correct": True},
    {"type": "slider", "text": "Năm?", "min": 2000, "max": 2030, "step": 1, "answer": 2023, "tolerance": 1},
    {"type": "pin", "text": "Ở đâu?", "media": {"kind": "image", "url": "/files/map.png"},
     "zone": {"shape": "circle", "x": 0.5, "y": 0.5, "r": 0.1}},
    {"type": "order", "text": "Xếp", "items": [{"text": "1"}, {"text": "2"}, {"text": "3"}]},
    {"type": "match", "text": "Ghép", "pairs": [{"left": "a", "right": "A"}, {"left": "b", "right": "B"}]},
    {"type": "type", "text": "Gõ", "accept": ["Prompt", "lời nhắc"]},
    {"type": "poll", "text": "Thích?", "options": [{"text": "Có"}, {"text": "Không"}]},
    {"type": "cloud", "text": "Một từ"},
]


class QuestionsTest(unittest.TestCase):
    def setUp(self):
        self.qs = make(SAMPLE)

    def test_all_ten_types_valid(self):
        self.assertEqual([q["type"] for q in self.qs], [s["type"] for s in SAMPLE])

    def test_public_view_never_leaks_answers(self):
        secret_keys = {"correct", "answer", "tolerance", "zone", "accept", "pairs", "explain"}
        for q in self.qs:
            v = Q.public_view(q, seed="room|u@x")
            self.assertFalse(secret_keys & set(v), (q["type"], set(v)))
            blob = json.dumps(v)
            for a in q.get("accept") or []:
                self.assertNotIn(a, blob)

    def test_order_public_never_in_correct_order(self):
        q = self.qs[5]
        for seed in ("a", "b", "c", None, "x|y"):
            v = Q.public_view(q, seed=seed)
            self.assertNotEqual([i["id"] for i in v["items"]], [i["id"] for i in q["items"]])

    def test_shuffle_stable_per_seed_and_differs(self):
        q = make([{"type": "single", "text": "x", "options": [{"text": str(i)} for i in range(6)], "correct": [0]}])[0]
        a1 = [o["id"] for o in Q.public_view(q, "s|u1")["options"]]
        self.assertEqual(a1, [o["id"] for o in Q.public_view(q, "s|u1")["options"]])
        others = {tuple(o["id"] for o in Q.public_view(q, "s|u%d" % i)["options"]) for i in range(20)}
        self.assertGreater(len(others), 5)

    def test_ids_regenerated_not_positional(self):
        again = Q.require_valid(SAMPLE, lambda: "%06x" % random.getrandbits(24))
        self.assertNotEqual(self.qs[0]["options"][0]["id"], again[0]["options"][0]["id"])

    def test_grading(self):
        s, m, tf, sl, pin, order, match, typ, poll, cloud = self.qs
        self.assertEqual(Q.grade(s, Q.clean_answer(s, {"o": s["correct"][0]})), 1.0)
        self.assertEqual(Q.grade(m, Q.clean_answer(m, {"o": m["correct"]})), 1.0)
        self.assertEqual(Q.grade(m, Q.clean_answer(m, {"o": m["correct"][:1]})), 0.0)
        self.assertEqual(Q.grade(tf, {"o": "t"}), 1.0)
        self.assertEqual(Q.grade(sl, {"v": 2024}), 1.0)
        self.assertEqual(Q.grade(sl, {"v": 2026}), 0.0)          # lech 3 = 3*max(1,1) -> 0
        self.assertTrue(0 < Q.grade(sl, {"v": 2025}) < 0.5)
        self.assertEqual(Q.grade(pin, {"x": 0.55, "y": 0.5}), 1.0)
        self.assertEqual(Q.grade(pin, {"x": 0.8, "y": 0.8}), 0.0)
        self.assertEqual(Q.grade(order, {"o": [i["id"] for i in order["items"]]}), 1.0)
        self.assertEqual(Q.grade(order, {"o": [i["id"] for i in order["items"]][::-1]}), 0.0)
        right = {p["id"]: p["rid"] for p in match["pairs"]}
        self.assertEqual(Q.grade(match, {"m": right}), 1.0)
        wrong = dict(zip(right.keys(), list(right.values())[::-1]))
        self.assertEqual(Q.grade(match, {"m": wrong}), 0.0)
        self.assertEqual(Q.grade(typ, {"t": "  PROMPT. "}), 1.0)
        self.assertEqual(Q.grade(typ, {"t": "loi nhac"}), 1.0)   # khong dau
        self.assertEqual(Q.grade(typ, {"t": "abc"}), 0.0)
        self.assertIsNone(Q.grade(poll, {"o": poll["options"][0]["id"]}))
        self.assertIsNone(Q.grade(cloud, {"t": "x"}))

    def test_clean_answer_rejects_garbage(self):
        s, m = self.qs[0], self.qs[1]
        for bad in ({"o": "zzz"}, {}, "x", {"o": ["a"]}):
            with self.assertRaises(QuizError):
                Q.clean_answer(s, bad)
        with self.assertRaises(QuizError):
            Q.clean_answer(m, {"o": []})
        match = self.qs[6]
        r = match["pairs"][0]["rid"]
        with self.assertRaises(QuizError):
            Q.clean_answer(match, {"m": {match["pairs"][0]["id"]: r, match["pairs"][1]["id"]: r}})

    def test_validation_errors_collected(self):
        with self.assertRaises(FieldErrors) as cm:
            Q.require_valid([{"type": "single", "text": "x", "options": [{"text": "a"}], "correct": [0]},
                             {"type": "slider", "text": "y", "min": 5, "max": 1, "answer": 3},
                             {"type": "pin", "text": "z"}, {"type": "nope", "text": "q"}])
        self.assertEqual(set(cm.exception.errors), {"q1", "q2", "q3", "q4"})

    def test_media_url_rejects_javascript(self):
        q = make([dict(SAMPLE[0], media={"url": "javascript:alert(1)"})])[0]
        self.assertIsNone(q["media"])

    def test_tally(self):
        s = self.qs[0]
        t = Q.tally(s, [{"o": s["options"][0]["id"]}, {"o": s["options"][0]["id"]}])
        self.assertEqual(t["options"][s["options"][0]["id"]], 2)
        c = Q.tally(self.qs[9], [{"t": "AI"}, {"t": "ai "}, {"t": "Claude"}])
        self.assertEqual(c["words"][0], ("ai", 2))


class ScoringTest(unittest.TestCase):
    S = settings.clean_settings({})

    def test_speed(self):
        self.assertEqual(scoring.speed_points(0, 20000), 1000)
        self.assertEqual(scoring.speed_points(20000, 20000), 500)
        self.assertEqual(scoring.speed_points(99999, 20000), 500)
        self.assertEqual(scoring.speed_points(10000, 20000, by_speed=False), 1000)

    def test_streak_and_double(self):
        r = scoring.score_answer(1.0, 0, 20000, 0, False, self.S)
        self.assertEqual((r["points"], r["streak"]), (1000, 1))
        r = scoring.score_answer(1.0, 0, 20000, 6, False, self.S)
        self.assertEqual(r["points"], 1500)                       # +500 tran
        r = scoring.score_answer(1.0, 0, 20000, 1, True, self.S)
        self.assertEqual(r["points"], 2200)                       # (1000+100)*2
        r = scoring.score_answer(0.5, 0, 20000, 3, False, self.S)
        self.assertEqual((r["points"], r["streak"], r["correct"]), (500, 0, False))
        r = scoring.score_answer(None, 0, 20000, 3, False, self.S)
        self.assertEqual((r["points"], r["streak"]), (0, 3))

    def test_fast_flag(self):
        self.assertTrue(scoring.fast_flag([(500, True), (300, True), (700, True)]))
        self.assertFalse(scoring.fast_flag([(500, True), (900, True), (700, True)]))
        self.assertFalse(scoring.fast_flag([(500, True), (300, False), (700, True)]))


class ProfileTest(unittest.TestCase):
    def test_names(self):
        for ok in ("Nguyễn An", "Đan Thanh", "Ngư Ông", "Hà Chó Con", "Lớn Bé"):
            self.assertEqual(profile.clean_nickname(ok), ok)
        for bad in ("thằng ngu", "đồ đần", "FuckBoy", "vcl", "a", "x" * 17, "<b>hi</b>"):
            with self.assertRaises(QuizError, msg=bad):
                profile.clean_nickname(bad)

    def test_avatar(self):
        self.assertEqual(profile.clean_avatar({"b": 99, "g": "2", "e": -1, "a": None}),
                         {"b": 0, "g": 2, "e": 0, "a": 0})


def P(u, score, dept, correct=0, ms=0):
    return {"user": u, "score": score, "department": dept, "correct_count": correct, "correct_ms": ms,
            "nickname": u}


class BoardPrizeTest(unittest.TestCase):
    def setUp(self):
        self.players = ([P("a%d" % i, 1000 + i * 100, "Ops", correct=i) for i in range(5)] +
                        [P("b%d" % i, 2000, "Fin", correct=5) for i in range(4)] +
                        [P("c0", 5000, "IT", correct=5), P("z", 0, None)])

    def test_rank_and_ties(self):
        r = board.rank_players(self.players + [P("k", 9999, "IT")] and self.players)
        self.assertEqual(r[0]["user"], "c0")
        tie = board.rank_players([P("x", 10, "a", ms=500), P("y", 10, "a", ms=300)])
        self.assertEqual(tie[0]["user"], "y")

    def test_teams_average_and_merge(self):
        teams = board.rank_teams(self.players)
        names = [t["team"] for t in teams]
        self.assertIn(C.TEAM_MERGED, names)              # IT (1) + chua co phong (1) -> gop
        self.assertNotIn("IT", names)
        fin = next(t for t in teams if t["team"] == "Fin")
        self.assertEqual(fin["score"], 2000)
        self.assertEqual(teams[0]["team"], C.TEAM_MERGED)  # (5000+0)/2 = 2500

    def test_allocate(self):
        ranked = board.rank_players(self.players)
        teams = board.rank_teams(self.players)
        rows = prizes.clean_prizes(None) + [{"scope": "team", "rank": "team1", "tickets": 1, "gift": ""},
                                             {"scope": "team", "rank": "team_mvp", "tickets": 0, "gift": "Áo"}]
        rows = prizes.clean_prizes(rows)
        aw = prizes.allocate(rows, ranked, teams, scored_total=5)
        r1 = [a for a in aw if a["rank"] == "rank1"]
        self.assertEqual(r1[0]["user"], "c0")
        passed = {a["user"] for a in aw if a["rank"] == "pass60"}
        self.assertEqual(passed, {"a3", "a4", "b0", "b1", "b2", "b3", "c0"})
        t1 = {a["user"] for a in aw if a["rank"] == "team1"}
        self.assertEqual(t1, {"c0", "z"})
        self.assertNotIn("z", {a["user"] for a in aw if a["rank"] in ("rank1", "rank2", "rank3")})

    def test_bad_prize_rows(self):
        for bad in ([{"scope": "player", "rank": "team1", "tickets": 1}],
                    [{"scope": "player", "rank": "rank1", "tickets": 0, "gift": ""}]):
            with self.assertRaises(QuizError):
                prizes.clean_prizes(bad)
        self.assertEqual(prizes.clean_prizes([{"scope": "player", "rank": "rank1", "tickets": 9}])[0]["tickets"], 3)

    def test_climb(self):
        ranked = board.rank_players([P("a", 3000, "x"), P("b", 2000, "x"), P("c", 100, "x")])
        cl = board.climbs(ranked, {"a": 3, "b": 1, "c": 2})
        aw = prizes.allocate([{"scope": "player", "rank": "climb", "tickets": 1, "gift": ""}], ranked, [], 3, cl)
        self.assertEqual(aw[0]["user"], "a")


class RoomTest(unittest.TestCase):
    def test_flow(self):
        ph, i = room.transition("start", "lobby", 0, 3, players=2)
        self.assertEqual((ph, i), ("question", 0))
        with self.assertRaises(QuizError):
            room.transition("next", "question", 0, 3)
        ph, i = room.transition("lock", ph, i, 3)
        ph, i = room.transition("reveal", ph, i, 3)
        ph, i = room.transition("next", ph, i, 3)
        self.assertEqual((ph, i), ("question", 1))
        with self.assertRaises(QuizError):
            room.transition("next", "reveal", 2, 3)
        with self.assertRaises(QuizError):
            room.transition("start", "lobby", 0, 3, players=0)
        self.assertEqual(room.transition("end", "board", 1, 3)[0], "ended")
        with self.assertRaises(QuizError):
            room.transition("cancel", "ended", 1, 3)

    def test_board_rules(self):
        self.assertEqual(room.next_action("reveal", 0, 3, "each"), "board")
        self.assertEqual(room.next_action("reveal", 2, 3, "each"), "end")
        self.assertEqual(room.next_action("reveal", 0, 10, "five"), "next")
        self.assertEqual(room.next_action("reveal", 4, 10, "five"), "board")

    def test_timing(self):
        dl = room.deadline_ms(1000, 20)
        self.assertEqual(dl, 1000 + 23000)
        self.assertTrue(room.accepting("question", dl + 500, dl))
        self.assertFalse(room.accepting("question", dl + 700, dl))
        self.assertEqual(room.elapsed_ms(1000, 2000), 0)

    def test_code(self):
        rng = random.Random(1)
        c = room.make_code(rng, set())
        self.assertEqual(len(c), 6)
        self.assertNotEqual(c[0], "0")


class SettingsTicketLessonTest(unittest.TestCase):
    def test_settings(self):
        s = settings.clean_settings({"guard": "basic", "show_on_phone": "0", "mode": "x"})
        self.assertEqual((s["guard"], s["show_on_phone"], s["mode"]), ("basic", False, "solo"))
        self.assertFalse(settings.shuffles_options(s))
        self.assertFalse(settings.shuffles_options(settings.clean_settings({"show_on_phone": False})))

    def test_tickets(self):
        self.assertEqual(tickets.week_start(datetime.date(2026, 11, 15)), datetime.date(2026, 11, 9))
        self.assertEqual(tickets.grant(2, 3), 1)
        self.assertEqual(tickets.grant(3, 1), 0)

    def test_lesson(self):
        with self.assertRaises(FieldErrors):
            lesson.clean_lesson({"title": "", "video_url": "javascript:x"})
        l = lesson.clean_lesson({"title": "Bài 1", "quiz": "Q-1", "practice_prompt": "Làm"})
        self.assertEqual(lesson.step(l, {}), "view")
        self.assertEqual(lesson.step(l, {"viewed_at": 1}), "quiz")
        self.assertEqual(lesson.step(l, {"viewed_at": 1, "quiz_score": 0}), "practice")
        self.assertEqual(lesson.step(l, {"viewed_at": 1, "quiz_score": 2, "practice_at": 1}), "done")
        qs = make(SAMPLE[:3])
        g = lesson.grade_self_quiz(qs, {qs[0]["id"]: {"o": qs[0]["correct"][0]}, qs[2]["id"]: {"o": "zz"}})
        self.assertEqual((g["score"], g["scored"]), (1, 3))
        with self.assertRaises(QuizError):
            lesson.clean_practice("ngắn", "")


class ImporterTest(unittest.TestCase):
    def test_kahoot(self):
        rows = [["Kahoot template"], [], ["", "Question - max 120", "Answer 1", "Answer 2", "Answer 3", "Answer 4",
                                          "Time limit (sec)", "Correct answer(s)"],
                ["", "Q1?", "A", "B", "C", "", 20, "2"],
                ["", "Q2?", "True", "False", "", "", 10, 1],
                ["", "Q3?", "A", "B", "C", "D", 30, "1,3"]]
        qs = Q.require_valid(importer.parse(rows), rid_seq())
        self.assertEqual([q["type"] for q in qs], ["single", "truefalse", "multi"])
        self.assertEqual(qs[0]["correct"], [qs[0]["options"][1]["id"]])

    def test_wayground(self):
        rows = [["Question Text", "Question Type", "Option 1", "Option 2", "Option 3", "Option 4", "Option 5",
                 "Correct Answer", "Time in seconds", "Image Link", "Answer explanation"],
                ["Q?", "Multiple Choice", "x", "y", "", "", "", 2, 30, "", "vì"],
                ["Gõ?", "Fill-in-the-Blank", "abc", "ABC", "", "", "", "", 20, "", ""]]
        qs = Q.require_valid(importer.parse(rows), rid_seq())
        self.assertEqual(qs[0]["explain"], "vì")
        self.assertEqual(qs[1]["type"], "type")

    def test_bad_file(self):
        with self.assertRaises(QuizError):
            importer.parse([["hello"], ["world"]])


if __name__ == "__main__":
    unittest.main()
