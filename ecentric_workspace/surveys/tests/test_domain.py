# Copyright (c) 2026, eCentric and contributors
"""Nghiep vu thuan cua Khao sat - chay khong can bench:

    python -m unittest ecentric_workspace.surveys.tests.test_domain
"""
import datetime
import unittest

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import (answers, audience, lifecycle, rewards, schema,
                                               summary, templates)
from ecentric_workspace.surveys.domain.errors import SurveyError


def form(*items):
    return schema.normalize({"items": list(items)})


def Q(qid, qtype, **kw):
    d = {"id": qid, "kind": "question", "type": qtype, "title": kw.pop("title", "Cau " + qid)}
    d.update(kw)
    return d


def S(sid, **kw):
    d = {"id": sid, "kind": "section", "title": kw.pop("title", "Phan " + sid)}
    d.update(kw)
    return d


def opts(*ids, **goto):
    return [{"id": i, "label": i.upper(), "goto": goto.get(i, "")} for i in ids]


class FixedRng:
    """random() tra lan luot cac so cho san; sample() lay n phan tu dau."""

    def __init__(self, *vals):
        self.vals = list(vals)

    def random(self):
        return self.vals.pop(0)

    def sample(self, pool, n):
        return list(pool)[:n]

    def shuffle(self, seq):
        seq.sort()

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]


# ----------------------------------------------------------------------------- schema --
class TestNormalize(unittest.TestCase):
    def test_strips_unknown_keys_and_coerces(self):
        f = form(Q("q1", "scale", scale_min="0", scale_max="99", evil="<script>", required="1"))
        q = f["items"][0]
        self.assertNotIn("evil", q)
        self.assertEqual((q["scale_min"], q["scale_max"], q["required"]), (0, 10, True))

    def test_unknown_type_falls_back_to_short_text(self):
        self.assertEqual(form(Q("q1", "hack"))["items"][0]["type"], C.Q_SHORT)

    def test_duplicate_and_bad_ids_are_replaced(self):
        f = form(Q("q1", "short_text"), Q("q1", "short_text"), Q("bad id!", "short_text"))
        ids = [it["id"] for it in f["items"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids[0], "q1")

    def test_reserved_ids_cannot_be_used(self):
        f = form(S("__submit__"), S("__start__"))
        self.assertNotIn("__submit__", [it["id"] for it in f["items"]])
        self.assertNotIn("__start__", [it["id"] for it in f["items"]])

    def test_draft_with_empty_title_still_saves(self):
        f = form({"kind": "question", "type": "single", "title": "", "options": []})
        self.assertEqual(f["items"][0]["title"], "")

    def test_rejects_non_dict_and_too_many(self):
        with self.assertRaises(SurveyError):
            schema.normalize([1, 2])
        with self.assertRaises(SurveyError):
            schema.normalize({"items": [Q("q%d" % i, "short_text") for i in range(C.MAX_ITEMS + 1)]})

    def test_quiz_correct_limited_to_real_options(self):
        f = form(Q("q1", "single", options=opts("a", "b"), correct=["a", "zzz"], points=2))
        self.assertEqual(f["items"][0]["correct"], ["a"])

    def test_points_zeroed_for_ungradable_types(self):
        self.assertEqual(form(Q("q1", "paragraph", points=5))["items"][0]["points"], 0)

    def test_goto_kept_only_when_branching_on(self):
        f = form(Q("q1", "single", options=opts("a", "b", b="s2")), S("s2"))
        self.assertNotIn("goto", f["items"][0]["options"][0])
        f = form(Q("q1", "single", branch=True, options=opts("a", "b", b="s2")), S("s2"))
        self.assertEqual(f["items"][0]["options"][1]["goto"], "s2")


class TestPublishProblems(unittest.TestCase):
    def test_empty_form(self):
        self.assertEqual(schema.publish_problems(form()), ["Khảo sát chưa có câu hỏi nào."])

    def test_ok_form_has_no_problems(self):
        f = form(Q("q1", "single", options=opts("a", "b")), Q("q2", "paragraph"))
        self.assertEqual(schema.publish_problems(f), [])

    def test_missing_title_and_options(self):
        p = schema.publish_problems(form(Q("q1", "single", title="", options=[])))
        self.assertTrue(any("chưa có nội dung" in x for x in p))
        self.assertTrue(any("chưa có lựa chọn" in x for x in p))

    def test_backward_jump_rejected(self):
        f = form(S("s1"), Q("q1", "single", branch=True, options=opts("a", a="s1")), S("s2"))
        self.assertTrue(any("không nằm sau" in x for x in schema.publish_problems(f)))
        f = form(S("s1"), Q("q1", "short_text"), S("s2", next="s1"), Q("q2", "short_text"))
        self.assertTrue(any("NẰM SAU" in x for x in schema.publish_problems(f)))

    def test_anonymous_file_question_rejected(self):
        f = form(Q("q1", "file"))
        self.assertEqual(schema.publish_problems(f), [])
        self.assertTrue(schema.publish_problems(f, anonymous=True))

    def test_quiz_points_need_answer_key(self):
        f = form(Q("q1", "single", options=opts("a"), points=1))
        self.assertTrue(schema.publish_problems(f, quiz=True))
        self.assertEqual(schema.publish_problems(f, quiz=False), [])

    def test_duplicate_option_labels(self):
        f = form(Q("q1", "single", options=[{"label": "Có"}, {"label": "có"}]))
        self.assertTrue(any("trùng" in x for x in schema.publish_problems(f)))

    def test_all_templates_are_publishable(self):
        for t in templates.TEMPLATES:
            with self.subTest(t=t["key"]):
                f = schema.normalize(t["form"])
                st = t["settings"]
                self.assertEqual(schema.publish_problems(
                    f, anonymous=bool(st.get("anonymous")), quiz=bool(st.get("is_quiz"))), [])


# ---------------------------------------------------------------------------- answers --
class TestPath(unittest.TestCase):
    def setUp(self):
        self.f = form(
            Q("q1", "single", branch=True, options=opts("yes", "no", "skip", no="s3", skip="__submit__")),
            S("s2"), Q("q2", "short_text", required=True),
            S("s3"), Q("q3", "short_text", required=True),
        )

    def test_default_walks_all_sections(self):
        self.assertEqual(answers.path(self.f, {}), ["__start__", "s2", "s3"])

    def test_branch_jumps_forward(self):
        self.assertEqual(answers.path(self.f, {"q1": {"sel": ["no"]}}), ["__start__", "s3"])

    def test_branch_submit_ends(self):
        self.assertEqual(answers.path(self.f, {"q1": {"sel": ["skip"]}}), ["__start__"])

    def test_required_only_on_visited_sections(self):
        clean, errors = answers.clean(self.f, {"q1": {"sel": ["no"]}, "q3": "x"})
        self.assertEqual(errors, {})
        self.assertEqual(set(clean), {"q1", "q3"})

    def test_answers_on_skipped_sections_are_dropped(self):
        clean, _e = answers.clean(self.f, {"q1": {"sel": ["skip"]}, "q2": "leak", "q3": "leak"})
        self.assertEqual(set(clean), {"q1"})

    def test_fake_option_cannot_branch(self):
        clean, errors = answers.clean(self.f, {"q1": {"sel": ["evil"]}, "q2": "a", "q3": "b"})
        self.assertNotIn("q1", clean)
        self.assertEqual(errors, {})

    def test_section_next_used_when_no_branch(self):
        f = form(S("s1", next="s3"), Q("q1", "short_text"), S("s2"), Q("q2", "short_text"),
                 S("s3"), Q("q3", "short_text"))
        self.assertEqual(answers.path(f, {}), ["s1", "s3"])

    def test_backward_target_never_loops(self):
        f = form(S("s1"), Q("q1", "single", branch=True, options=opts("a", a="s1")), S("s2"))
        self.assertEqual(answers.path(f, {"q1": {"sel": ["a"]}}), ["s1", "s2"])


class TestClean(unittest.TestCase):
    def one(self, q, raw):
        return answers.clean_one(form(q)["items"][0], raw)

    def test_short_validations(self):
        num = Q("q", "short_text", validation={"kind": "number", "min": 1, "max": 10})
        self.assertEqual(self.one(num, "5"), ("5", None))
        self.assertTrue(self.one(num, "11")[1])
        self.assertTrue(self.one(num, "abc")[1])
        self.assertTrue(self.one(Q("q", "short_text", validation={"kind": "email"}), "a@b")[1])
        self.assertIsNone(self.one(Q("q", "short_text", validation={"kind": "email"}), "a@b.vn")[1])
        self.assertIsNone(self.one(Q("q", "short_text", validation={"kind": "phone"}), "0901 234 567")[1])
        ln = Q("q", "paragraph", validation={"kind": "length", "min": 5})
        self.assertTrue(self.one(ln, "abc")[1])

    def test_single_other_and_multi_limits(self):
        single = Q("q", "single", options=opts("a", "b"), allow_other=True)
        self.assertEqual(self.one(single, {"sel": ["a", "b"]}), ({"sel": ["a"]}, None))
        self.assertEqual(self.one(single, {"sel": ["a"], "other": "x"}), ({"sel": [], "other": "x"}, None))
        multi = Q("q", "multi", options=opts("a", "b", "c"), min_select=2, max_select=2)
        self.assertTrue(self.one(multi, {"sel": ["a"]})[1])
        self.assertIsNone(self.one(multi, {"sel": ["a", "b"]})[1])
        self.assertTrue(self.one(multi, {"sel": ["a", "b", "c"]})[1])
        drop = Q("q", "dropdown", options=opts("a"))
        self.assertEqual(self.one(drop, "a"), ({"sel": ["a"]}, None))
        self.assertEqual(self.one(drop, {"sel": [], "other": "x"}), (None, None))

    def test_scale_rating(self):
        self.assertEqual(self.one(Q("q", "scale", scale_min=0, scale_max=10), "7"), (7, None))
        self.assertTrue(self.one(Q("q", "scale"), 9)[1])
        self.assertEqual(self.one(Q("q", "rating", rating_max=5), 0), (None, None))
        self.assertTrue(self.one(Q("q", "rating", rating_max=5), 6)[1])

    def test_grid(self):
        g = Q("q", "grid_single", rows=[{"id": "r1", "label": "A"}, {"id": "r2", "label": "B"}],
              cols=[{"id": "c1", "label": "x"}], require_each_row=True)
        self.assertTrue(self.one(g, {"r1": "c1"})[1])
        self.assertEqual(self.one(g, {"r1": "c1", "r2": "c1", "r9": "c1"}), ({"r1": "c1", "r2": "c1"}, None))
        gm = Q("q", "grid_multi", rows=[{"id": "r1", "label": "A"}], cols=[{"id": "c1", "label": "x"}])
        self.assertEqual(self.one(gm, {"r1": ["c1", "c1", "zz"]}), ({"r1": ["c1"]}, None))

    def test_ranking_must_be_permutation(self):
        r = Q("q", "ranking", options=opts("a", "b", "c"))
        self.assertEqual(self.one(r, ["c", "a", "b"]), (["c", "a", "b"], None))
        self.assertTrue(self.one(r, ["a", "a", "b"])[1])

    def test_date_time_file(self):
        self.assertEqual(self.one(Q("q", "date"), "2026-02-28"), ("2026-02-28", None))
        self.assertTrue(self.one(Q("q", "date"), "2026-02-30")[1])
        self.assertTrue(self.one(Q("q", "time"), "25:00")[1])
        fq = Q("q", "file", max_files=1)
        self.assertTrue(self.one(fq, [{"url": "/files/public.png"}])[1])
        self.assertTrue(self.one(fq, [{"url": "/private/files/a"}, {"url": "/private/files/b"}])[1])
        self.assertEqual(self.one(fq, [{"url": "/private/files/a.pdf"}])[0][0]["name"], "a.pdf")

    def test_required_message_and_first_error(self):
        f = form(Q("q1", "short_text"), Q("q2", "short_text", required=True))
        _c, errors = answers.clean(f, {})
        self.assertEqual(answers.first_error(f, errors), "Câu 2: Câu này bắt buộc.")


class TestScore(unittest.TestCase):
    def test_score(self):
        f = form(Q("q1", "single", options=opts("a", "b"), correct=["a"], points=1),
                 Q("q2", "multi", options=opts("a", "b", "c"), correct=["a", "c"], points=2),
                 Q("q3", "short_text", correct=["Ha Noi", "hà nội"], points=1),
                 Q("q4", "paragraph"))
        res = answers.score(f, {"q1": {"sel": ["a"]}, "q2": {"sel": ["a"]}, "q3": "  HÀ NỘI "})
        self.assertEqual((res["score"], res["max_score"]), (2, 4))
        self.assertEqual(res["detail"], {"q1": True, "q2": False, "q3": True})


# --------------------------------------------------------------------------- audience --
class TestAudience(unittest.TestCase):
    DEPTS = [{"name": "All"}, {"name": "Ops", "parent_department": "All"},
             {"name": "Ops-HN", "parent_department": "Ops"}, {"name": "Fin", "parent_department": "All"}]
    EMPS = [{"user_id": "a@x", "department": "Ops-HN", "status": "Active"},
            {"user_id": "b@x", "department": "Fin", "status": "Active"},
            {"user_id": "c@x", "department": "Ops", "status": "Left"},
            {"user_id": "", "department": "Ops", "status": "Active"}]

    def elig(self, mode, targets):
        return audience.eligible_users(mode, targets, self.EMPS, self.DEPTS)

    def test_all_means_active_with_user(self):
        self.assertEqual(self.elig("all", []), {"a@x", "b@x"})

    def test_department_includes_children(self):
        self.assertEqual(self.elig("custom", [{"kind": "Department", "department": "Ops"}]), {"a@x"})

    def test_named_users_and_exclusion_wins(self):
        t = [{"kind": "Department", "department": "All"}, {"kind": "User", "user": "admin@x"},
             {"kind": "Exclude", "user": "a@x"}, {"kind": "Exclude", "user": "admin@x"}]
        self.assertEqual(self.elig("custom", t), {"b@x"})
        self.assertEqual(self.elig("all", [{"kind": "Exclude", "user": "b@x"}]), {"a@x"})

    def test_custom_with_nothing_selected_is_empty(self):
        self.assertEqual(self.elig("custom", []), set())

    def test_cycle_in_tree_does_not_hang(self):
        depts = [{"name": "A", "parent_department": "B"}, {"name": "B", "parent_department": "A"}]
        emps = [{"user_id": "u", "department": "A", "status": "Active"}]
        self.assertEqual(audience.eligible_users("custom", [{"kind": "Department", "department": "B"}],
                                                 emps, depts), {"u"})

    def test_describe(self):
        self.assertEqual(audience.describe("all", [{"kind": "Exclude", "user": "x"}]), "Cả công ty (trừ 1 người)")
        self.assertEqual(audience.describe("custom", [{"kind": "Department", "department": "Ops"},
                                                      {"kind": "User", "user": "u"}]), "Ops + 1 người")


# ---------------------------------------------------------------------------- rewards --
class TestRewards(unittest.TestCase):
    def prizes(self, *qty):
        return [{"id": "p%d" % i, "label": "P%d" % i, "quantity": q, "awarded": 0}
                for i, q in enumerate(qty)]

    def test_windows_cover_every_spin_once(self):
        self.assertEqual(rewards.windows(1, 100, 3), [(1, 33), (34, 66), (67, 100)])
        self.assertEqual(rewards.windows(1, 2, 5), [(1, 1), (2, 2)])
        for n, k in ((100, 3), (7, 7), (50, 4), (13, 5)):
            seen = [x for a, b in rewards.windows(1, n, k) for x in range(a, b + 1)]
            self.assertEqual(seen, list(range(1, n + 1)), (n, k))

    def test_plan_one_prize_per_window(self):
        """PO 01/10: 3 qua, 100 nguoi -> 1-33 mot qua, 34-66 mot qua, 67-100 mot qua."""
        import random
        for seed in range(200):
            slots = rewards.plan(self.prizes(1, 2), 100, 0, random.Random(seed))
            self.assertEqual([(s["from"], s["to"]) for s in slots], [(1, 33), (34, 66), (67, 100)])
            for s in slots:
                self.assertTrue(s["from"] <= s["seq"] <= s["to"])
            self.assertEqual(sorted(s["prize"] for s in slots), ["p0", "p1", "p1"])

    def test_first_three_cannot_take_everything(self):
        import random
        for seed in range(300):
            slots = rewards.plan(self.prizes(3), 100, 0, random.Random(seed))
            early = [rewards.spin_result(slots, q, self.prizes(3)) for q in (1, 2, 3)]
            self.assertLessEqual(sum(1 for x in early if x), 1, seed)

    def test_every_position_has_equal_odds(self):
        """Ty le trung theo tung vi tri ~ K/E (3/99 = 1/33) - dau, giua, cuoi nhu nhau."""
        import random
        rng, hits, runs = random.Random(7), {1: 0, 50: 0, 99: 0}, 20000
        for _ in range(runs):
            slots = rewards.plan(self.prizes(3), 99, 0, rng)
            for q in hits:
                if rewards.spin_result(slots, q, self.prizes(3)):
                    hits[q] += 1
        for q, h in hits.items():
            self.assertAlmostEqual(h / float(runs), 1 / 33.0, delta=0.006, msg=q)

    def test_exact_count_and_leftover_dropped(self):
        """Du nguoi -> phat DUNG so qua; it nguoi hon -> qua cua dot chua toi khong trao (PO "B")."""
        import random
        for seed in range(50):
            prizes = self.prizes(3)
            slots = rewards.plan(prizes, 60, 0, random.Random(seed))
            for q in range(1, 61):
                pid = rewards.spin_result(slots, q, prizes)
                if pid:
                    prizes[0]["awarded"] += 1
            self.assertEqual(prizes[0]["awarded"], 3)
            prizes = self.prizes(3)
            for q in range(1, 30):              # 29 nguoi quay tren 60 du kien
                if rewards.spin_result(slots, q, prizes):
                    prizes[0]["awarded"] += 1
            self.assertLessEqual(prizes[0]["awarded"], 2)

    def test_replan_keeps_past_and_spreads_rest(self):
        prizes = self.prizes(4)
        prizes[0]["awarded"] = 1
        slots = rewards.plan(prizes, 100, 40, FixedRng())
        self.assertEqual([(s["from"], s["to"]) for s in slots], [(41, 60), (61, 80), (81, 100)])
        self.assertEqual(rewards.plan(self.prizes(0), 100, 0, FixedRng()), [])

    def test_spin_result_ignores_exhausted_prize(self):
        slots = [{"from": 1, "to": 5, "seq": 3, "prize": "p0"}]
        self.assertEqual(rewards.spin_result(slots, 3, self.prizes(1)), "p0")
        self.assertIsNone(rewards.spin_result(slots, 2, self.prizes(1)))
        done = self.prizes(1)
        done[0]["awarded"] = 1
        self.assertIsNone(rewards.spin_result(slots, 3, done))

    def test_wave_info_hides_seq(self):
        slots = [{"from": 1, "to": 33, "seq": 20, "prize": "p0"}, {"from": 34, "to": 66, "seq": 50, "prize": "p1"}]
        w = rewards.wave_info(slots, 41, self.prizes(1, 1))
        self.assertEqual(w["current"], 2)
        self.assertEqual([x["state"] for x in w["waves"]], ["done", "open"])
        self.assertNotIn("seq", w["waves"][0])

    def test_lucky_draw_whole_range_and_empty_numbers(self):
        rng = FixedRng()
        res = rewards.lucky_draw(self.prizes(1, 2), {1: "a", 3: "c"}, 100, rng)
        self.assertEqual([r["prize"] for r in res], ["p1", "p1", "p0"])       # giai nho truoc
        self.assertEqual([r["rank"] for r in res], [2, 2, 1])
        self.assertEqual([r["number"] for r in res], [1, 2, 3])
        self.assertEqual([r["user"] for r in res], ["a", None, "c"])          # so 2 trong -> de lai
        self.assertEqual(len(set(r["number"] for r in rewards.lucky_draw(self.prizes(50), {}, 30, rng))), 30)

    def test_assign_missing_gives_free_numbers_to_unpicked(self):
        rng = FixedRng()
        self.assertEqual(rewards.assign_missing(4, {1: "a"}, ["c", "a", "b"], rng), {2: "b", 3: "c"})
        self.assertEqual(rewards.assign_missing(2, {1: "a"}, ["a", "b", "c"], rng), {2: "b"})   # het so
        self.assertEqual(rewards.assign_missing(5, {1: "a", 2: "b"}, ["a", "b"], rng), {})      # ai cung co so

    def test_free_number(self):
        self.assertEqual(rewards.free_number(3, {1, 2}, FixedRng()), 3)
        self.assertIsNone(rewards.free_number(2, {1, 2}, FixedRng()))

    def test_race_everyone_gets_a_cart(self):
        r = rewards.race(self.prizes(1, 1), ["b", "a", "c", "a"], FixedRng())
        self.assertEqual(sorted(r["order"]), ["a", "b", "c"])
        self.assertEqual([(w["place"], w["rank"], w["user"]) for w in r["winners"]], [(1, 1, "a"), (2, 2, "b")])
        self.assertEqual(rewards.race(self.prizes(5), ["a"], FixedRng())["winners"][0]["user"], "a")

    def test_format_number(self):
        self.assertEqual(rewards.format_number(7), "007")
        self.assertEqual(rewards.format_number(7, 1000), "0007")
        self.assertEqual(rewards.format_number(100, 100), "100")


# ---------------------------------------------------------------------------- summary --
class TestSummary(unittest.TestCase):
    def test_counts_average_nps(self):
        f = form(Q("q1", "single", options=opts("a", "b"), allow_other=True),
                 Q("q2", "scale", scale_min=0, scale_max=10),
                 Q("q3", "paragraph"),
                 Q("q4", "ranking", options=opts("x", "y")))
        rows = [{"q1": {"sel": ["a"]}, "q2": 10, "q3": "tốt", "q4": ["x", "y"]},
                {"q1": {"sel": [], "other": "khác"}, "q2": 3, "q4": ["y", "x"]},
                {"q1": {"sel": ["a"]}, "q2": 9}]
        s = summary.summarize(f, rows)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["questions"]["q1"]["counts"], {"a": 2, "b": 0})
        self.assertEqual(s["questions"]["q1"]["other"], 1)
        self.assertEqual(s["questions"]["q2"]["nps"], 33)
        self.assertEqual(s["questions"]["q3"]["samples"], ["tốt"])
        self.assertEqual(s["questions"]["q4"]["average_rank"], {"x": 1.5, "y": 1.5})
        pub = summary.public_summary(f, rows)
        self.assertNotIn("samples", pub["questions"]["q3"])
        self.assertNotIn("other_samples", pub["questions"]["q1"])


class TestLifecycle(unittest.TestCase):
    def test_effective(self):
        t = datetime.datetime(2026, 10, 1, 12)
        h = datetime.timedelta(hours=1)
        E = lifecycle.effective_status
        self.assertEqual(E("Draft", None, None, t), "draft")
        self.assertEqual(E("Open", None, None, t), "open")
        self.assertEqual(E("Open", t + h, None, t), "scheduled")
        self.assertEqual(E("Open", None, t, t), "closed")
        self.assertEqual(E("Open", None, None, t, responses=5, limit=5), "closed")
        self.assertEqual(E("Closed", None, None, t), "closed")


if __name__ == "__main__":
    unittest.main()
