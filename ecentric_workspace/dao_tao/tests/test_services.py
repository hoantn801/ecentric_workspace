# Copyright (c) 2026, eCentric and contributors
"""Service Dao tao / Quiz chay ngoai Frappe: FakeRepo + frappe gia (chi de import).

    python -m unittest ecentric_workspace.dao_tao.tests.test_services
"""
import json
import random
import sys
import types
import unittest


def _install_fake_frappe():
    if "frappe" in sys.modules:
        return
    fr = types.ModuleType("frappe")
    for n in ("ValidationError", "PermissionError", "DoesNotExistError", "DuplicateEntryError"):
        setattr(fr, n, type(n, (Exception,), {}))
    fr.whitelist = lambda *a, **k: (lambda f: f)
    utils = types.ModuleType("frappe.utils")
    utils.strip_html = lambda s: s
    utils.now_datetime = None
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils


_install_fake_frappe()

from ecentric_workspace.dao_tao import constants as C  # noqa: E402
from ecentric_workspace.dao_tao.application import (learn_service, play_service, quiz_service,  # noqa: E402
                                                    room_service)
from ecentric_workspace.dao_tao.application.access import Ctx  # noqa: E402
from ecentric_workspace.dao_tao.domain.errors import (FieldErrors, QuizError,  # noqa: E402
                                                      QuizPermissionError)
from ecentric_workspace.dao_tao.tests.fake_repo import FakeRepo  # noqa: E402
from ecentric_workspace.dao_tao.tests.test_domain import SAMPLE  # noqa: E402

HOST = Ctx("host@x", ["EC Training Host"])
HR = Ctx("hr@x", ["HR User"])
STAFF = [Ctx("p%d@x" % i, ["Employee"]) for i in range(6)]


def build_quiz(repo, qs=None, settings=None, prizes=None):
    out = quiz_service.save(HOST, repo, {"title": "Buổi 1", "status": "Ready", "questions": qs or SAMPLE[:4],
                                         "settings": settings or {}, "prizes": prizes})
    return out["quiz"]["name"]


def secret_in(blob, q):
    """True neu payload gui may nguoi choi lo dap an cau q."""
    s = json.dumps(blob, ensure_ascii=False)
    if '"correct"' in s or '"accept"' in s or '"zone"' in s or '"tolerance"' in s:
        return True
    return False


class QuizFlowTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()
        for i, c in enumerate(STAFF):
            self.repo.emps[c.user] = {"employee_name": "Nhân Viên %d" % i,
                                      "department": "Ops" if i < 4 else "Fin"}
        self.quiz = build_quiz(self.repo)
        self.room = room_service.open_room(HOST, self.repo, self.quiz, rng=random.Random(3))
        self.code, self.sess = self.room["code"], self.room["session"]

    def act(self, action):
        s = self.repo.get_session(self.sess)
        if action == "reveal" and s["phase"] == "reveal":     # het gio / du nguoi da tu cong bo
            return room_service.host_state(HOST, self.repo, self.sess)
        return room_service.act(HOST, self.repo, self.sess, action, s["version"])["state"]

    def join_all(self, n=6):
        for c in STAFF[:n]:
            play_service.join(c, self.repo, self.code, device="dev-" + c.user)

    def correct_payload(self, user, idx=None):
        s = self.repo.get_session(self.sess)
        q = s["questions"][s["index"] if idx is None else idx]
        if q["type"] in ("single", "truefalse"):
            return {"o": q["correct"][0]}
        if q["type"] == "multi":
            return {"o": q["correct"]}
        if q["type"] == "slider":
            return {"v": q["answer"]}
        raise AssertionError(q["type"])

    def wrong_payload(self):
        s = self.repo.get_session(self.sess)
        q = s["questions"][s["index"]]
        if q["type"] == "slider":
            return {"v": q["min"]}
        bad = [o["id"] for o in q["options"] if o["id"] not in q["correct"]]
        return {"o": bad[0]} if q["type"] != "multi" else {"o": bad}

    def answer(self, ctx, payload, wait_ms=3500):
        self.repo.tick(wait_ms)
        s = self.repo.get_session(self.sess)
        return play_service.answer(ctx, self.repo, self.code, s["questions"][s["index"]]["id"], payload,
                                   device="dev-" + ctx.user)

    # ------------------------------------------------------------------------------
    def test_permissions(self):
        with self.assertRaises(QuizPermissionError):
            room_service.open_room(STAFF[0], self.repo, self.quiz)
        with self.assertRaises(QuizPermissionError):
            quiz_service.save(STAFF[0], self.repo, {"title": "x"})
        with self.assertRaises(QuizPermissionError):
            room_service.act(STAFF[0], self.repo, self.sess, "start")
        with self.assertRaises(QuizPermissionError):
            room_service.host_state(STAFF[0], self.repo, self.sess)
        self.assertTrue(room_service.open_room(HR, self.repo, self.quiz)["code"])
        self.assertTrue(room_service.open_room(Ctx("admin@x", ["System Manager"]), self.repo, self.quiz))

    def test_full_game(self):
        self.join_all()
        st = self.act("start")
        self.assertEqual(st["phase"], "question")
        # Truoc 3 giay chuan bi: tu choi
        with self.assertRaises(QuizError):
            self.answer(STAFF[0], self.correct_payload(STAFF[0].user), wait_ms=100)
        # Nguoi choi khong nhan dap an
        ps = play_service.state(STAFF[0], self.repo, self.code)
        self.assertFalse(secret_in(ps, None))
        self.assertIn("question", ps)
        self.assertFalse(secret_in(room_service.host_state(HOST, self.repo, self.sess), None))
        # p0 dung nhanh, p1 dung cham, p2 sai, p3..p5 khong tra loi
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user), wait_ms=3000)
        with self.assertRaises(QuizError):
            self.answer(STAFF[0], self.correct_payload(STAFF[0].user), wait_ms=10)
        self.answer(STAFF[1], self.correct_payload(STAFF[1].user), wait_ms=10000)
        self.answer(STAFF[2], self.wrong_payload(), wait_ms=10)
        ps = play_service.state(STAFF[0], self.repo, self.code)
        self.assertTrue(ps["answered"])
        self.assertNotIn("result", ps)
        # het gio -> tu khoa khi co nguoi doc
        self.repo.tick(20000)
        with self.assertRaises(QuizError):
            self.answer(STAFF[3], self.correct_payload(STAFF[3].user), wait_ms=10)
        ps = play_service.state(STAFF[3], self.repo, self.code)
        self.assertEqual(ps["phase"], "reveal")
        self.assertIn("result", ps)               # het gio -> cong bo luon
        st = self.act("reveal")
        self.assertEqual(st["phase"], "reveal")
        self.assertIn("reveal", st)
        p0 = play_service.state(STAFF[0], self.repo, self.code)
        self.assertTrue(p0["result"]["correct"])
        self.assertEqual(p0["me"]["rank"], 1)
        p1 = play_service.state(STAFF[1], self.repo, self.code)
        self.assertLess(p1["result"]["points"], p0["result"]["points"])
        self.assertFalse(play_service.state(STAFF[2], self.repo, self.code)["result"]["correct"])
        # Cac cau con lai
        for i in range(1, 4):
            nxt = st["next_action"]
            if nxt == "board":
                st = self.act("board")
                self.assertTrue(st["board"])
            st = self.act("next")
            self.assertEqual(st["index"], i)
            self.repo.tick(3000)
            for c in STAFF:
                self.answer(c, self.correct_payload(c.user), wait_ms=200)
            # moi nguoi tra loi -> khoa ngay
            self.assertEqual(self.repo.get_session(self.sess)["phase"], "reveal")
            st = self.act("reveal")
        self.assertEqual(st["next_action"], "end")
        st = self.act("end")
        self.assertEqual(st["phase"], "ended")
        final = st["final"]
        self.assertEqual(final["podium"][0]["email"], STAFF[0].user)
        self.assertEqual(len(final["teams"]), 2)            # Ops (4) + Fin (2 -> Van phong)
        self.assertIn(C.TEAM_MERGED, [t["team"] for t in final["teams"]])
        r1 = [a for a in final["awards"] if a["rank"] == "rank1"]
        self.assertEqual(r1[0]["user"], STAFF[0].user)
        self.assertEqual(r1[0]["granted"], 3)                # 3 ve hang 1 (+1 ve 60%) -> tran 3
        res = play_service.ended_state(STAFF[0], self.repo, self.sess)
        self.assertEqual(res["final"]["my_rank"], 1)
        self.assertTrue(res["final"]["awards"])
        # Ve tuan: p0 du tran 3, p1 hang 2 = 2 ve + 60% = 1 -> 3
        self.assertEqual(self.repo.tickets_in_week(STAFF[0].user, self._ws()), 3)
        with self.assertRaises(QuizError):
            self.act("next")
        hist = play_service.history(STAFF[0], self.repo)
        self.assertEqual(hist["played"][0]["rank"], 1)

    def _ws(self):
        from ecentric_workspace.dao_tao.domain import tickets
        return tickets.week_start(self.repo.now())

    def test_last_question_double_and_streak(self):
        qid = build_quiz(self.repo, qs=[SAMPLE[0], SAMPLE[2]], settings={"by_speed": False})
        r = room_service.open_room(HOST, self.repo, qid)
        self.code, self.sess = r["code"], r["session"]
        self.join_all(1)
        self.act("start")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        self.act("reveal")
        self.act("board")
        self.act("next")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        self.act("reveal")
        p = self.repo.get_player(self.sess, STAFF[0].user)
        self.assertEqual(p["score"], 1000 + (1000 + 100) * 2)
        self.assertEqual(p["best_streak"], 2)

    def test_device_and_kick(self):
        play_service.join(STAFF[0], self.repo, self.code, device="A")
        with self.assertRaises(QuizError):
            play_service.join(STAFF[0], self.repo, self.code, device="B")
        self.assertIn("device", self.repo.get_player(self.sess, STAFF[0].user)["flags"])
        room_service.manage_player(HOST, self.repo, self.sess, STAFF[0].user, "reset_device")
        play_service.join(STAFF[0], self.repo, self.code, device="B")
        room_service.manage_player(HOST, self.repo, self.sess, STAFF[0].user, "kick")
        with self.assertRaises(QuizError):
            play_service.join(STAFF[0], self.repo, self.code, device="B")

    def test_automation_blocked_standard_not_basic(self):
        with self.assertRaises(QuizError):
            play_service.join(STAFF[0], self.repo, self.code, automation=True)
        qid = build_quiz(self.repo, settings={"guard": "basic"})
        r = room_service.open_room(HOST, self.repo, qid)
        self.assertTrue(play_service.join(STAFF[0], self.repo, r["code"], automation=True)["joined"])

    def test_profile_and_bad_name(self):
        play_service.join(STAFF[0], self.repo, self.code, device="A")
        with self.assertRaises(QuizError):
            play_service.set_profile(STAFF[0], self.repo, self.code, nickname="thằng ngu")
        st = play_service.set_profile(STAFF[0], self.repo, self.code, nickname="Siêu Nhân", avatar={"b": 2, "a": 3})
        self.assertEqual(st["me"]["nickname"], "Siêu Nhân")
        self.assertEqual(st["me"]["email"], STAFF[0].user)
        self.assertEqual(self.repo.get_profile(STAFF[0].user)["avatar"]["a"], 3)
        # lan sau vao phong khac dung lai ho so
        r = room_service.open_room(HOST, self.repo, self.quiz)
        st = play_service.join(STAFF[0], self.repo, r["code"], device="A")
        self.assertEqual(st["me"]["nickname"], "Siêu Nhân")
        room_service.manage_player(HOST, self.repo, r["session"], STAFF[0].user, "rename", "Tên Mới")
        self.assertEqual(play_service.state(STAFF[0], self.repo, r["code"])["me"]["nickname"], "Tên Mới")

    def test_nick_disabled(self):
        qid = build_quiz(self.repo, settings={"allow_nick": False})
        r = room_service.open_room(HOST, self.repo, qid)
        play_service.join(STAFF[0], self.repo, r["code"])
        st = play_service.set_profile(STAFF[0], self.repo, r["code"], nickname="Đổi Tên")
        self.assertNotEqual(st["me"]["nickname"], "Đổi Tên")

    def test_tiles_only_mode_no_shuffle_no_text(self):
        qid = build_quiz(self.repo, settings={"show_on_phone": False})
        r = room_service.open_room(HOST, self.repo, qid)
        self.code, self.sess = r["code"], r["session"]
        self.join_all(2)
        self.act("start")
        a = play_service.state(STAFF[0], self.repo, self.code)["question"]
        b = play_service.state(STAFF[1], self.repo, self.code)["question"]
        self.assertTrue(a["tiles_only"])
        self.assertEqual([o["id"] for o in a["options"]], [o["id"] for o in b["options"]])
        self.assertEqual(a["text"], "")

    def test_shuffle_differs_per_player(self):
        qs = [{"type": "single", "text": "x", "options": [{"text": str(i)} for i in range(6)], "correct": [0]}]
        for same, want_many in ((False, True), (True, False)):
            qid = build_quiz(self.repo, qs=qs, settings={"same_order": same})
            r = room_service.open_room(HOST, self.repo, qid)
            self.code, self.sess = r["code"], r["session"]
            self.join_all(6)
            self.act("start")
            orders = {tuple(o["id"] for o in play_service.state(c, self.repo, self.code)["question"]["options"])
                      for c in STAFF}
            self.assertEqual(len(orders) > 1, want_many)      # mac dinh: cung thu tu nhu may chieu

    def test_start_needs_player_and_stale_version(self):
        with self.assertRaises(QuizError):
            self.act("start")
        self.join_all(1)
        out = room_service.act(HOST, self.repo, self.sess, "start", expect_version=999)
        self.assertTrue(out["stale"])
        self.assertEqual(self.repo.get_session(self.sess)["phase"], "lobby")

    def test_end_early_mid_question_and_cancel(self):
        self.join_all(2)
        self.act("start")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        st = self.act("end")
        self.assertEqual(st["phase"], "ended")
        self.assertEqual(st["final"]["podium"][0]["email"], STAFF[0].user)
        self.assertGreater(self.repo.get_player(self.sess, STAFF[0].user)["score"], 0)
        with self.assertRaises(QuizError):
            play_service.state(STAFF[0], self.repo, self.code)     # ma phong het hieu luc
        r = room_service.open_room(HOST, self.repo, self.quiz)
        room_service.act(HOST, self.repo, r["session"], "cancel")
        self.assertEqual(self.repo.get_session(r["session"])["phase"], "cancelled")

    def test_answer_wrong_qid_and_garbage(self):
        self.join_all(2)
        self.act("start")
        self.repo.tick(3500)
        with self.assertRaises(QuizError):
            play_service.answer(STAFF[0], self.repo, self.code, "khac", {"o": "x"})
        s = self.repo.get_session(self.sess)
        with self.assertRaises(QuizError):
            play_service.answer(STAFF[0], self.repo, self.code, s["questions"][0]["id"], {"o": "zzz"})
        with self.assertRaises(QuizError):
            play_service.answer(Ctx("ghost@x", []), self.repo, self.code, s["questions"][0]["id"],
                                self.correct_payload(""))

    def test_fast_flag(self):
        qid = build_quiz(self.repo, qs=[SAMPLE[0]] * 4)
        r = room_service.open_room(HOST, self.repo, qid)
        self.code, self.sess = r["code"], r["session"]
        self.join_all(2)
        self.act("start")
        for i in range(3):
            self.answer(STAFF[0], self.correct_payload(STAFF[0].user), wait_ms=3200)
            self.answer(STAFF[1], self.correct_payload(STAFF[1].user), wait_ms=3000)
            self.act("reveal")
            self.act("board")
            self.act("next")
        flags = room_service.host_state(HOST, self.repo, self.sess)["flags"]
        self.assertEqual([f["email"] for f in flags], [STAFF[0].user])

    def test_kicked_answer_does_not_lock_early(self):
        self.join_all(3)
        self.act("start")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        room_service.manage_player(HOST, self.repo, self.sess, STAFF[0].user, "kick")
        self.answer(STAFF[1], self.correct_payload(STAFF[1].user), wait_ms=10)
        self.assertEqual(self.repo.get_session(self.sess)["phase"], "question")   # p2 chua tra loi
        self.answer(STAFF[2], self.correct_payload(STAFF[2].user), wait_ms=10)
        self.assertEqual(self.repo.get_session(self.sess)["phase"], "reveal")

    def test_late_join_keeps_board_and_salt(self):
        self.join_all(2)
        self.act("start")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        self.act("reveal")
        salt = self.repo.get_session(self.sess)["state"]["salt"]
        play_service.join(STAFF[5], self.repo, self.code, device="z")
        st = self.repo.get_session(self.sess)["state"]
        self.assertTrue(st["board"])
        self.assertEqual(st["salt"], salt)
        self.assertNotIn("salt", json.dumps(play_service.state(STAFF[5], self.repo, self.code)))
        self.assertNotIn(salt, json.dumps(room_service.host_state(HOST, self.repo, self.sess)))

    def test_locked_phase_hides_new_score(self):
        self.join_all(2)
        self.act("start")
        self.answer(STAFF[0], self.correct_payload(STAFF[0].user))
        self.act("lock")                                      # nguoi dan khoa tay (chua cong bo)
        ps = play_service.state(STAFF[0], self.repo, self.code)
        self.assertEqual(ps["phase"], "locked")
        self.assertEqual((ps["me"]["score"], ps["me"]["rank"]), (0, None))
        self.repo.tick(30000)
        self.assertEqual(play_service.state(STAFF[1], self.repo, self.code)["phase"], "locked")

    def test_live_card_and_kill_switch(self):
        rooms = play_service.live_card(STAFF[0], self.repo)["rooms"]
        self.assertEqual(rooms[0]["code"], self.code)
        self.assertNotIn("host", rooms[0])
        self.repo.cache.clear()
        self.repo.flags["ec_quiz_card_disabled"] = 1
        self.assertEqual(play_service.live_card(STAFF[0], self.repo)["rooms"], [])

    def test_unknown_code(self):
        with self.assertRaises(QuizError):
            play_service.join(STAFF[0], self.repo, "123")
        with self.assertRaises(QuizError):
            play_service.join(STAFF[0], self.repo, "999999")

    def test_quiz_save_optimistic_lock_and_draft(self):
        out = quiz_service.save(HOST, self.repo, {"title": "Nháp", "questions": [{"type": "single", "text": ""}]})
        self.assertIn("q1", out["errors"])
        name, mod = out["quiz"]["name"], out["quiz"]["modified"]
        quiz_service.save(HOST, self.repo, {"name": name, "title": "Nháp 2", "modified": mod})
        with self.assertRaises(QuizError):
            quiz_service.save(HOST, self.repo, {"name": name, "title": "Nháp 3", "modified": mod})
        with self.assertRaises(FieldErrors):
            quiz_service.save(HOST, self.repo, {"title": "x", "status": "Ready", "questions": []})
        with self.assertRaises(QuizError):
            room_service.open_room(HOST, self.repo, name)        # cau chua xong -> khong mo phong

    def test_import(self):
        self.repo.files["/files/k.xlsx"] = HOST.user
        self.repo.xlsx["/files/k.xlsx"] = [["Question", "Answer 1", "Answer 2", "Time limit", "Correct"],
                                           ["Q?", "A", "B", 20, 2]]
        out = quiz_service.import_file(HOST, self.repo, "/files/k.xlsx")
        self.assertEqual(out["count"], 1)
        self.repo.files["/files/o.xlsx"] = "other@x"
        with self.assertRaises(QuizError):
            quiz_service.import_file(HOST, self.repo, "/files/o.xlsx")


class LearnTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()
        self.quiz = build_quiz(self.repo, qs=SAMPLE)
        les = learn_service.admin_save(HOST, self.repo, {"title": "Bài 1", "status": "Published",
                                                         "quiz": self.quiz, "practice_prompt": "Viết prompt",
                                                         "week_start": "2026-11-09"})
        self.les = les["name"]

    def test_staff_cannot_manage(self):
        with self.assertRaises(QuizPermissionError):
            learn_service.admin_save(STAFF[0], self.repo, {"title": "x"})
        with self.assertRaises(QuizPermissionError):
            learn_service.admin_list(STAFF[0], self.repo)

    def test_flow_and_tickets(self):
        u = STAFF[0]
        hub = learn_service.hub(u, self.repo)
        self.assertEqual(hub["week"][0]["step"], "view")
        d = learn_service.lesson_detail(u, self.repo, self.les)
        self.assertEqual(d["step"], "quiz")
        self.assertFalse(secret_in(d["quiz"], None))
        # tra loi dung het cac cau cham
        qz = self.repo.get_quiz(self.quiz)
        ans = {}
        for q in qz["questions"]:
            if q["type"] in ("single", "truefalse"):
                ans[q["id"]] = {"o": q["correct"][0]}
            elif q["type"] == "multi":
                ans[q["id"]] = {"o": q["correct"]}
            elif q["type"] == "slider":
                ans[q["id"]] = {"v": q["answer"]}
            elif q["type"] == "pin":
                ans[q["id"]] = {"x": q["zone"]["x"], "y": q["zone"]["y"]}
            elif q["type"] == "order":
                ans[q["id"]] = {"o": [i["id"] for i in q["items"]]}
            elif q["type"] == "match":
                ans[q["id"]] = {"m": {p["id"]: p["rid"] for p in q["pairs"]}}
            elif q["type"] == "type":
                ans[q["id"]] = {"t": q["accept"][0]}
        g = learn_service.submit_quiz(u, self.repo, self.les, ans)
        self.assertEqual((g["score"], g["scored"]), (8, 8))
        self.assertEqual(g["ticket"], 1)
        g2 = learn_service.submit_quiz(u, self.repo, self.les, ans)
        self.assertEqual(g2["ticket"], 0)                    # lam lai: khong them ve
        with self.assertRaises(QuizError):
            learn_service.submit_practice(u, self.repo, self.les, "ngắn")
        p = learn_service.submit_practice(u, self.repo, self.les, "Mình đã dùng Claude viết email báo giá.")
        self.assertEqual(p["ticket"], 1)
        self.assertEqual(learn_service.lesson_detail(u, self.repo, self.les)["step"], "done")
        r = learn_service.admin_review(HOST, self.repo, self.les, u.user, "Revoked")
        self.assertTrue(r["ticket_revoked"])
        from ecentric_workspace.dao_tao.domain import tickets
        self.assertEqual(self.repo.tickets_in_week(u.user, tickets.week_start(self.repo.now())), 1)

    def test_quiz_ticket_only_first_submission(self):
        u = STAFF[1]
        learn_service.lesson_detail(u, self.repo, self.les)
        g = learn_service.submit_quiz(u, self.repo, self.les, {})          # nop trang -> xem dap an
        self.assertEqual(g["ticket"], 0)
        qz = self.repo.get_quiz(self.quiz)
        ans = {q["id"]: {"o": q["correct"][0]} for q in qz["questions"] if q["type"] in ("single", "truefalse")}
        self.assertEqual(learn_service.submit_quiz(u, self.repo, self.les, ans)["ticket"], 0)

    def test_publish_needs_ready_quiz(self):
        draft = quiz_service.save(HOST, self.repo, {"title": "Nháp", "questions": [{"type": "single", "text": ""}]})["quiz"]["name"]
        with self.assertRaises(QuizError):
            learn_service.admin_save(HOST, self.repo, {"title": "B", "status": "Published", "quiz": draft})
        self.assertTrue(learn_service.admin_save(HOST, self.repo, {"title": "B", "quiz": draft})["name"])

    def test_capped_week_does_not_regrant_later(self):
        from ecentric_workspace.dao_tao.application import ticket_service
        u = STAFF[2].user
        self.assertEqual(ticket_service.grant(self.repo, u, "manual", "a", 3, "x"), 3)
        self.assertEqual(ticket_service.grant(self.repo, u, "practice", "L1", 1, "bai"), 0)
        self.repo.tick(8 * 24 * 3600 * 1000)                      # sang tuan sau
        self.assertEqual(ticket_service.grant(self.repo, u, "practice", "L1", 1, "bai"), 0)
        self.assertEqual(ticket_service.grant(self.repo, u, "practice", "L2", 1, "bai 2"), 1)

    def test_draft_lesson_hidden(self):
        d = learn_service.admin_save(HOST, self.repo, {"title": "Nháp"})
        with self.assertRaises(QuizError):
            learn_service.lesson_detail(STAFF[0], self.repo, d["name"])
        self.assertEqual(len(learn_service.hub(STAFF[0], self.repo)["library"]), 1)

    def test_votes(self):
        u = STAFF[0]
        names = [learn_service.propose_topic(u, self.repo, {"title": "Chủ đề %d" % i})["name"] for i in range(4)]
        for n in names[:3]:
            learn_service.vote(u, self.repo, n, True)
        with self.assertRaises(QuizError):
            learn_service.vote(u, self.repo, names[3], True)
        learn_service.admin_topic(HOST, self.repo, names[0], "Done")
        t = learn_service.vote(u, self.repo, names[3], True)     # phieu chu de Done duoc tra lai
        self.assertEqual(t["left"], 0)
        learn_service.vote(u, self.repo, names[3], False)
        self.assertEqual(learn_service.topics(u, self.repo)["left"], 1)
        with self.assertRaises(QuizError):
            learn_service.vote(u, self.repo, names[0], True)      # chu de da xong


if __name__ == "__main__":
    unittest.main()
