# Copyright (c) 2026, eCentric and contributors
"""Service Khao sat chay ngoai Frappe: repository gia trong bo nho + frappe gia (chi de import).

    python -m unittest ecentric_workspace.surveys.tests.test_services

Di tron cac duong chinh: tao tu mau -> soan -> phat hanh -> hub -> nop (bat buoc, trung,
an danh, gioi han, sua) -> vong quay (khong vuot so qua) -> so may man + quay so -> ket qua.
"""
import copy
import datetime
import json
import sys
import types
import unittest


def _install_fake_frappe():
    if "frappe" in sys.modules and getattr(sys.modules["frappe"], "_survey_fake", False):
        return
    fr = types.ModuleType("frappe")
    fr._survey_fake = True

    class _E(Exception):
        pass
    for n in ("ValidationError", "PermissionError", "DoesNotExistError", "DuplicateEntryError"):
        setattr(fr, n, type(n, (_E,), {}))
    fr.whitelist = lambda *a, **k: (lambda f: f)
    utils = types.ModuleType("frappe.utils")
    utils.get_datetime = lambda v: v
    utils.now_datetime = datetime.datetime.now
    utils.strip_html = lambda s: s
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils


_install_fake_frappe()

from ecentric_workspace.surveys import constants as C  # noqa: E402
from ecentric_workspace.surveys.application import (builder_service, draw_feed,  # noqa: E402
                                                    draw_service, publish_service,
                                                    respond_service, results_service,
                                                    submit_reward)
from ecentric_workspace.surveys.application.access import Ctx  # noqa: E402
from ecentric_workspace.surveys.domain.errors import (AnswerErrors, SurveyError,  # noqa: E402
                                                      SurveyPermissionError)

NOW = datetime.datetime(2026, 10, 1, 9, 0)


class FakeRepo:
    def __init__(self):
        self.surveys, self.resps, self.parts, self.files = {}, {}, {}, {}
        self.notified, self.jobs, self.seq = [], [], 0
        self.clock, self.realtime, self.cache, self.flags, self.commits = NOW, [], {}, {}, 0
        self.emps = [{"user_id": u, "employee_name": u.split("@")[0].title(), "department": d,
                      "status": "Active"} for u, d in (("hr@x", "HR"), ("a@x", "Ops"),
                                                        ("b@x", "Ops-HN"), ("c@x", "Fin"))]
        self.depts = [{"name": "All", "department_name": "All"},
                      {"name": "HR", "parent_department": "All"},
                      {"name": "Ops", "parent_department": "All", "department_name": "Vận hành"},
                      {"name": "Ops-HN", "parent_department": "Ops"},
                      {"name": "Fin", "parent_department": "All"}]

    # -- tien ich
    def now(self):
        return self.clock

    def to_datetime(self, v):
        if not v:
            return None
        return v if isinstance(v, datetime.datetime) else datetime.datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")

    def _id(self, p):
        self.seq += 1
        return "%s%d" % (p, self.seq)

    # -- khao sat
    def get_survey(self, name):
        s = self.surveys.get(name)
        return copy.deepcopy(s) if s else None

    def lock_survey(self, name):
        pass

    def _children(self, rows, prefix):
        out = []
        for r in rows:
            r = dict(r)
            r.setdefault("name", self._id(prefix))
            out.append(r)
        return out

    def insert_survey(self, fields, children=None):
        name = "KS-%d" % (len(self.surveys) + 1)
        d = {"name": name, "owner": self.actor, "modified": "m0", "targets": [], "editors": [],
             "prizes": [], "response_count": 0, "lucky_seq": 0, "status": "Draft",
             "audience_mode": "all", "reward_mode": "none"}
        d.update(fields)
        for k, rows in (children or {}).items():
            d[k] = self._children(rows, k[0])
        self.surveys[name] = d
        return name

    def save_survey(self, name, fields, children=None):
        d = self.surveys[name]
        d.update(fields)
        for k, rows in (children or {}).items():
            d[k] = self._children(rows, k[0])
        d["modified"] = "m%d" % (int(d["modified"][1:]) + 1)
        return d["modified"]

    def set_survey_values(self, name, values):
        self.surveys[name].update(values)

    def update_survey(self, name, values):
        self.surveys[name].update(values)
        return self.save_survey(name, {})

    def set_prize_awarded(self, row, n):
        for s in self.surveys.values():
            for p in s["prizes"]:
                if p["name"] == row:
                    p["awarded"] = n

    def delete_survey(self, name):
        del self.surveys[name]

    def surveys_managed_by(self, user, all_surveys=False):
        return [copy.deepcopy(s) for s in self.surveys.values()
                if all_surveys or s["owner"] == user or user in [e["user"] for e in s["editors"]]]

    def surveys_by_status(self, status, names=None):
        return [copy.deepcopy(s) for s in self.surveys.values() if s["status"] == status]

    def surveys_by_names(self, names):
        return [copy.deepcopy(self.surveys[n]) for n in names if n in self.surveys]

    # -- phieu
    def count_responses(self, survey):
        return sum(1 for r in self.resps.values() if r["survey"] == survey)

    def responses(self, survey, limit=5000, start=0):
        rows = [copy.deepcopy(r) for r in self.resps.values() if r["survey"] == survey]
        rows.sort(key=lambda r: r["seq"], reverse=True)
        return rows[start:start + limit]

    def get_response(self, name):
        return copy.deepcopy(self.resps.get(name))

    def insert_response(self, survey, respondent, answers, score, max_score, at):
        n = self._id("R")
        self.resps[n] = {"name": n, "survey": survey, "respondent": respondent, "answers": answers,
                         "score": score, "max_score": max_score, "submitted_at": at, "seq": self.seq}
        return n

    def update_response(self, name, answers, score, max_score, at):
        self.resps[name].update({"answers": answers, "score": score, "updated_at": at})

    # -- tham gia
    def get_participant(self, survey, user):
        return copy.deepcopy(self.parts.get((survey, user)))

    def insert_participant(self, survey, user, fields):
        if (survey, user) in self.parts:
            return None
        d = {"name": self._id("P"), "survey": survey, "user": user, "reward_result": "", "lucky_number": 0}
        d.update(fields)
        self.parts[(survey, user)] = d
        return d["name"]

    def update_participant(self, name, values):
        for p in self.parts.values():
            if p["name"] == name:
                p.update(values)

    def participants(self, survey):
        return [copy.deepcopy(p) for (s, _u), p in self.parts.items() if s == survey]

    def participations_of(self, user):
        return [copy.deepcopy(p) for (s, u), p in self.parts.items() if u == user]

    def winners(self, surveys):
        return [copy.deepcopy(p) for (s, _u), p in self.parts.items()
                if s in surveys and p.get("reward_result") == "Win"]

    def count_spins(self, survey):
        return sum(1 for (s, _u), p in self.parts.items() if s == survey and p.get("reward_result"))

    def count_participants(self, survey):
        return sum(1 for (s, _u) in self.parts if s == survey)

    def _draws(self):
        out = [copy.deepcopy(s) for s in self.surveys.values()
               if s["status"] in ("Open", "Closed") and s.get("reward_mode") in C.SCHEDULED_MODES
               and s.get("draw_scheduled_at")]
        return sorted(out, key=lambda s: str(s["draw_scheduled_at"]))

    def pending_draws(self, until):
        return [s for s in self._draws() if not s.get("draw_at") and self.to_datetime(s["draw_scheduled_at"]) <= until]

    def draw_surveys(self, start, end):
        return [s for s in self._draws() if start <= self.to_datetime(s["draw_scheduled_at"]) <= end]

    def count_draw_surveys(self, start, end):
        return len(self.draw_surveys(start, end))

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def site_flag(self, key):
        return bool(self.flags.get(key))

    def publish_realtime(self, user, event, payload):
        self.realtime.append((user, event, payload))

    def cache_get(self, key):
        return self.cache.get(key)

    def cache_set(self, key, value, ttl):
        self.cache[key] = value

    def cache_delete(self, key):
        self.cache.pop(key, None)

    # -- to chuc / tep / thong bao
    def employees(self):
        return copy.deepcopy(self.emps)

    def departments(self):
        return copy.deepcopy(self.depts)

    def user_names(self, users):
        return {u: u.split("@")[0].title() for u in users if u}

    def user_exists(self, user):
        return user in [e["user_id"] for e in self.emps]

    def file_by_url(self, url):
        return copy.deepcopy(self.files.get(url))

    def attach_file(self, file_name, dt, dn):
        for f in self.files.values():
            if f["name"] == file_name:
                f.update({"attached_to_doctype": dt, "attached_to_name": dn})

    def file_content(self, name):
        return b"x", "x.pdf"

    def notify(self, user, title, message, url, survey, key):
        self.notified.append((user, title, url, key))

    def enqueue(self, method, **kw):
        self.jobs.append((method, kw))

    def log_error(self, title):
        raise AssertionError(title)


HR = Ctx("hr@x", ["HR Manager"])
A = Ctx("a@x", [])
B = Ctx("b@x", [])
CC = Ctx("c@x", [])


class Base(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.r.actor = "hr@x"

    def make(self, items=None, settings=None, targets=None, prizes=None, publish=True):
        name = builder_service.create(HR, repo=self.r)["name"]
        payload = {"settings": dict({"title": "Thử"}, **(settings or {})),
                   "form": {"items": items or [
                       {"id": "q1", "kind": "question", "type": "single", "title": "Hài lòng?",
                        "required": True, "options": [{"id": "y", "label": "Có"}, {"id": "n", "label": "Không"}]},
                       {"id": "q2", "kind": "question", "type": "paragraph", "title": "Góp ý"}]},
                   "targets": targets or [], "prizes": prizes or []}
        builder_service.save(HR, name, json.dumps(payload), repo=self.r)
        if publish:
            publish_service.publish(HR, name, repo=self.r)
        return name


class TestBuilder(Base):
    def test_create_needs_role(self):
        with self.assertRaises(SurveyPermissionError):
            builder_service.create(A, repo=self.r)

    def test_other_user_cannot_open_builder(self):
        name = self.make(publish=False)
        with self.assertRaises(SurveyPermissionError):
            builder_service.get(A, name, repo=self.r)

    def test_save_and_optimistic_lock(self):
        name = self.make(publish=False)
        got = builder_service.get(HR, name, repo=self.r)
        self.assertEqual(got["settings"]["title"], "Thử")
        self.assertEqual(len(got["form"]["items"]), 2)
        with self.assertRaises(SurveyError):
            builder_service.save(HR, name, {"modified": "old", "settings": {}}, repo=self.r)

    def test_editor_can_save_but_not_change_editors(self):
        name = self.make(publish=False)
        builder_service.save(HR, name, {"editors": [{"user": "a@x"}]}, repo=self.r)
        self.assertEqual([e["user"] for e in self.r.surveys[name]["editors"]], ["a@x"])
        builder_service.save(A, name, {"settings": {"title": "Đổi"}, "editors": []}, repo=self.r)
        self.assertEqual(self.r.surveys[name]["title"], "Đổi")
        self.assertEqual([e["user"] for e in self.r.surveys[name]["editors"]], ["a@x"])

    def test_duplicate_and_list(self):
        name = self.make(targets=[{"kind": "Department", "department": "Ops"}],
                         settings={"audience_mode": "custom"})
        copy_name = builder_service.create(HR, source=name, repo=self.r)["name"]
        dup = self.r.surveys[copy_name]
        self.assertEqual(dup["status"], "Draft")
        self.assertIn("bản sao", dup["title"])
        self.assertEqual(dup["targets"][0]["department"], "Ops")
        self.assertEqual(len(builder_service.list_mine(HR, repo=self.r)["surveys"]), 2)

    def test_prize_awarded_is_kept_and_protected(self):
        name = self.make(settings={"reward_mode": "wheel"}, prizes=[{"label": "Trà sữa", "quantity": 1}])
        pid = self.r.surveys[name]["prizes"][0]["name"]
        self.r.set_prize_awarded(pid, 1)
        builder_service.save(HR, name, {"prizes": [{"id": pid, "label": "Trà sữa", "quantity": 2}]}, repo=self.r)
        self.assertEqual(self.r.surveys[name]["prizes"][0]["awarded"], 1)
        with self.assertRaises(SurveyError):
            builder_service.save(HR, name, {"prizes": []}, repo=self.r)
        with self.assertRaises(SurveyError):
            builder_service.save(HR, name, {"settings": {"reward_mode": "none"}}, repo=self.r)


class TestPrivacyLocks(Base):
    def test_anonymous_locked_after_first_response(self):
        name = self.make(settings={"anonymous": 1})
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        with self.assertRaises(SurveyError):
            builder_service.save(HR, name, {"settings": {"anonymous": 0}}, repo=self.r)
        builder_service.save(HR, name, {"settings": {"anonymous": 1, "title": "x"}}, repo=self.r)

    def test_save_returns_prize_ids(self):
        name = self.make(settings={"reward_mode": "wheel"}, prizes=[{"label": "A", "quantity": 1}])
        res = builder_service.save(HR, name, {"prizes": [{"label": "A", "quantity": 1}, {"label": "B", "quantity": 2}]}, repo=self.r)
        self.assertEqual([p["label"] for p in res["prizes"]], ["A", "B"])
        self.assertTrue(all(p["id"] for p in res["prizes"]))


class TestPublish(Base):
    def test_custom_without_target_blocked(self):
        name = self.make(settings={"audience_mode": "custom"}, publish=False)
        with self.assertRaises(SurveyError) as cm:
            publish_service.publish(HR, name, repo=self.r)
        self.assertIn("Chưa chọn phòng ban", str(cm.exception))

    def test_publish_notifies_once(self):
        name = self.make()
        self.assertEqual(self.r.jobs[0][1], {"name": name, "kind": "open"})
        publish_service.close(HR, name, repo=self.r)
        publish_service.reopen(HR, name, repo=self.r)
        self.assertEqual(len(self.r.jobs), 1)
        res = publish_service.run_notify(name, repo=self.r)
        self.assertEqual(res["sent"], 4)
        self.assertTrue(all(n[2] == "/khao-sat/lam?s=" + name for n in self.r.notified))

    def test_remind_only_not_done(self):
        name = self.make()
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        publish_service.remind(HR, name, repo=self.r)
        self.assertEqual(self.r.jobs[-1][1]["users"], ["b@x", "c@x", "hr@x"])


class TestRespond(Base):
    def test_hub_respects_audience(self):
        self.make(settings={"audience_mode": "custom"},
                  targets=[{"kind": "Department", "department": "Ops"}, {"kind": "Exclude", "user": "a@x"}])
        self.assertEqual(len(respond_service.hub(B, repo=self.r)["open"]), 1)
        self.assertEqual(respond_service.hub(A, repo=self.r)["open"], [])
        self.assertEqual(respond_service.hub(CC, repo=self.r)["open"], [])
        with self.assertRaises(SurveyPermissionError):
            respond_service.get_form(CC, "KS-1", repo=self.r)

    def test_draft_hidden_from_respondents(self):
        name = self.make(publish=False)
        with self.assertRaises(SurveyError):
            respond_service.get_form(A, name, repo=self.r)
        self.assertTrue(respond_service.get_form(HR, name, preview=True, repo=self.r)["preview"])

    def test_answer_key_never_sent(self):
        name = self.make(settings={"is_quiz": 1}, items=[
            {"id": "q1", "kind": "question", "type": "single", "title": "1+1", "points": 1,
             "options": [{"id": "a", "label": "2"}, {"id": "b", "label": "3"}], "correct": ["a"]}])
        form = respond_service.get_form(A, name, repo=self.r)["form"]
        self.assertNotIn("correct", form["items"][0])
        res = respond_service.submit(A, name, {"q1": {"sel": ["a"]}}, repo=self.r)
        self.assertEqual(res["score"]["score"], 1)

    def test_required_duplicate_and_count(self):
        name = self.make()
        with self.assertRaises(AnswerErrors) as cm:
            respond_service.submit(A, name, {}, repo=self.r)
        self.assertEqual(cm.exception.errors, {"q1": "Câu này bắt buộc."})
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}, "q2": "ok"}, repo=self.r)
        with self.assertRaises(SurveyError):
            respond_service.submit(A, name, {"q1": {"sel": ["n"]}}, repo=self.r)
        self.assertEqual(self.r.surveys[name]["response_count"], 1)
        self.assertEqual(respond_service.hub(A, repo=self.r)["done"][0]["name"], name)

    def test_anonymous_keeps_no_link(self):
        name = self.make(settings={"anonymous": 1})
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        resp = list(self.r.resps.values())[0]
        self.assertIsNone(resp["respondent"])
        self.assertIsNone(self.r.parts[(name, "a@x")]["response"])
        self.assertEqual(results_service.response_at(HR, name, 0, repo=self.r)["respondent"], "")
        self.assertNotIn("Email", results_service.export(HR, name, repo=self.r)[1][0])

    def test_allow_edit_updates_same_response(self):
        name = self.make(settings={"allow_edit": 1})
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        self.assertEqual(respond_service.get_form(A, name, repo=self.r)["my_answers"], {"q1": {"sel": ["y"]}})
        res = respond_service.submit(A, name, {"q1": {"sel": ["n"]}}, repo=self.r)
        self.assertTrue(res["edited"])
        self.assertEqual(len(self.r.resps), 1)
        self.assertEqual(list(self.r.resps.values())[0]["answers"], {"q1": {"sel": ["n"]}})

    def test_limit_and_closed(self):
        name = self.make(settings={"response_limit": 1})
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        with self.assertRaises(SurveyError):
            respond_service.submit(B, name, {"q1": {"sel": ["y"]}}, repo=self.r)
        name2 = self.make(settings={"close_at": "2026-10-01T10:00"})
        self.r.surveys[name2]["close_at"] = "2026-09-30 10:00:00"
        with self.assertRaises(SurveyError):
            respond_service.submit(A, name2, {"q1": {"sel": ["y"]}}, repo=self.r)

    def test_foreign_file_rejected(self):
        name = self.make(items=[{"id": "f", "kind": "question", "type": "file", "title": "CV"}])
        self.r.files["/private/files/x.pdf"] = {"name": "F1", "owner": "b@x", "is_private": 1}
        with self.assertRaises(SurveyError):
            respond_service.submit(A, name, {"f": [{"url": "/private/files/x.pdf"}]}, repo=self.r)
        self.r.files["/private/files/x.pdf"]["owner"] = "a@x"
        respond_service.submit(A, name, {"f": [{"url": "/private/files/x.pdf"}]}, repo=self.r)
        self.assertEqual(self.r.files["/private/files/x.pdf"]["attached_to_doctype"], C.RESPONSE)
        content, _f = results_service.file_for_download(HR, name, "/private/files/x.pdf", repo=self.r)
        self.assertEqual(content, b"x")


class FixedRng:
    """Ngau nhien "co dinh": lay phan tu dau, khong xao tron, randint = dau dot."""

    def __init__(self, v=0.0):
        self.v = v

    def random(self):
        return self.v

    def sample(self, pool, n):
        return list(pool)[:n]

    def shuffle(self, seq):
        pass

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]


def ok(c):
    return {"q1": {"sel": ["y"]}}


class TestRewards(Base):
    def setUp(self):
        super().setUp()
        self._rng = (submit_reward._RNG, draw_service._RNG)
        submit_reward._RNG = draw_service._RNG = FixedRng()

    def tearDown(self):
        submit_reward._RNG, draw_service._RNG = self._rng

    def at(self, minutes):
        return (NOW + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")

    def test_wheel_needs_submission_and_spins_once(self):
        name = self.make(settings={"reward_mode": "wheel", "wheel_expected": 2},
                         prizes=[{"label": "Trà sữa", "quantity": 1}])
        with self.assertRaises(SurveyError):
            submit_reward.spin(A, name, self.r)
        res = respond_service.submit(A, name, ok(A), repo=self.r)
        self.assertTrue(res["reward"]["can_spin"])
        out = submit_reward.spin(A, name, self.r)
        self.assertEqual((out["result"], out["prize_label"]), ("Win", "Trà sữa"))
        with self.assertRaises(SurveyError):
            submit_reward.spin(A, name, self.r)
        respond_service.submit(B, name, ok(B), repo=self.r)
        self.assertEqual(submit_reward.spin(B, name, self.r)["result"], "Lose")
        self.assertEqual(self.r.surveys[name]["prizes"][0]["awarded"], 1)
        board = respond_service.hub(B, repo=self.r)["board"]
        self.assertEqual(board[0]["prize"], "Trà sữa")

    def test_wheel_one_prize_per_wave(self):
        """4 nguoi, 2 qua -> dot 1 (luot 1-2) mot qua, dot 2 (luot 3-4) mot qua."""
        name = self.make(settings={"reward_mode": "wheel"}, prizes=[{"label": "Nước", "quantity": 2}])
        plan = json.loads(self.r.surveys[name]["wheel_plan"])
        self.assertEqual([(p["from"], p["to"], p["seq"]) for p in plan], [(1, 2, 1), (3, 4, 3)])
        got = []
        for c in (A, B, CC, HR):
            respond_service.submit(c, name, ok(c), repo=self.r)
            got.append(submit_reward.spin(c, name, self.r))
        self.assertEqual([g["result"] for g in got], ["Win", "Lose", "Win", "Lose"])
        self.assertEqual([g["waves"]["seq"] for g in got], [1, 2, 3, 4])
        self.assertEqual(got[1]["waves"]["current"], 1)
        self.assertNotIn("seq", got[1]["waves"]["waves"][0])          # khong lo luot trung
        self.assertNotIn("wheel_plan", json.dumps(respond_service.get_form(A, name, repo=self.r)))
        self.assertNotIn("wheel_plan", json.dumps(builder_service.get(HR, name, repo=self.r)))

    def test_wheel_replans_when_prizes_change_midway(self):
        name = self.make(settings={"reward_mode": "wheel"}, prizes=[{"label": "Nước", "quantity": 1}])
        respond_service.submit(A, name, ok(A), repo=self.r)
        submit_reward.spin(A, name, self.r)                                # luot 1 trung (dau dot)
        got = builder_service.get(HR, name, repo=self.r)
        prizes = [dict(p, quantity=2) for p in got["prizes"]]
        builder_service.save(HR, name, json.dumps({"settings": got["settings"], "prizes": prizes,
                                                   "targets": [], "modified": got["modified"]}), repo=self.r)
        plan = json.loads(self.r.surveys[name]["wheel_plan"])
        self.assertEqual([(p["from"], p["to"]) for p in plan], [(2, 4)])

    def test_scheduled_mode_needs_time_and_range(self):
        with self.assertRaises(SurveyError) as e:
            self.make(settings={"reward_mode": "lucky_number"}, prizes=[{"label": "Nước", "quantity": 1}])
        self.assertIn("giờ quay", str(e.exception))
        with self.assertRaises(SurveyError) as e:
            self.make(settings={"reward_mode": "lucky_number", "draw_scheduled_at": self.at(-1)},
                      prizes=[{"label": "Nước", "quantity": 1}])
        self.assertIn("đã qua", str(e.exception))
        self.r.emps += [{"user_id": "u%d@x" % i, "employee_name": "U", "department": "HR", "status": "Active"}
                        for i in range(10)]
        with self.assertRaises(SurveyError) as e:
            self.make(settings={"reward_mode": "lucky_number", "number_range": 10,
                                "draw_scheduled_at": self.at(60)}, prizes=[{"label": "Nước", "quantity": 1}])
        self.assertIn("Dải số", str(e.exception))

    def test_lucky_number_pick_notify_and_draw(self):
        name = self.make(settings={"reward_mode": "lucky_number", "number_range": 10,
                                   "draw_scheduled_at": self.at(60)},
                         prizes=[{"label": "Tai nghe", "quantity": 1}, {"label": "Trà sữa", "quantity": 1}])
        with self.assertRaises(SurveyError):
            submit_reward.pick_number(A, name, 3, self.r)                  # chua nop
        respond_service.submit(A, name, ok(A), repo=self.r)
        respond_service.submit(B, name, ok(B), repo=self.r)
        self.assertEqual(submit_reward.pick_number(A, name, 3, self.r)["lucky_number"], "003")
        with self.assertRaises(SurveyError):
            submit_reward.pick_number(B, name, 3, self.r)                  # trung so
        with self.assertRaises(SurveyError):
            submit_reward.pick_number(B, name, 11, self.r)                 # ngoai dai
        st = submit_reward.pick_number(B, name, 0, self.r)                 # may chon giup
        self.assertEqual(st["lucky_number"], "001")
        self.assertEqual([h["label"] for h in st["board"]["holders"]], ["001", "003"])
        self.assertEqual(submit_reward.pick_number(A, name, 5, self.r)["number"], 5)   # doi so
        self.assertEqual(self.r.surveys[name]["lucky_seq"], 2)

        self.assertEqual(draw_service.tick(self.r), {"notified": 0, "drawn": 0})    # 09:00, quay 10:00
        self.r.clock = NOW + datetime.timedelta(minutes=55)
        self.assertEqual(draw_service.tick(self.r), {"notified": 1, "drawn": 0})
        self.assertEqual(draw_service.tick(self.r), {"notified": 0, "drawn": 0})    # khong bao trung
        job = self.r.jobs[-1]
        self.assertEqual(job[0], draw_service.NOTIFY_JOB)
        self.assertEqual(draw_service.notify_soon(repo=self.r, **job[1])["sent"], 4)
        soon = [n for n in self.r.notified if "|draw_soon|" in n[3]]
        self.assertEqual(len(soon), 4)
        self.assertEqual({u for u, ev, _p in self.r.realtime}, {"hr@x", "a@x", "b@x", "c@x"})

        self.r.clock = NOW + datetime.timedelta(minutes=60)
        self.assertEqual(draw_service.tick(self.r)["drawn"], 1)
        self.assertEqual(draw_service.tick(self.r)["drawn"], 0)                     # chay lai: khong doi
        data = json.loads(self.r.surveys[name]["draw_results"])
        # quay giai nho truoc: so 1 (B) trung Tra sua, so 2 trong -> Tai nghe de lai
        self.assertEqual([(i["label"], i["number"], i["user"]) for i in data["items"]],
                         [("Trà sữa", 1, "b@x"), ("Tai nghe", 2, None)])
        self.assertEqual(self.r.parts[(name, "b@x")]["reward_result"], "Win")
        self.assertEqual(self.r.parts[(name, "a@x")]["reward_result"], "Lose")
        self.assertEqual([p["awarded"] for p in self.r.surveys[name]["prizes"]], [0, 1])
        self.assertEqual(len([n for n in self.r.notified if n[3].startswith("survey|win|")]), 1)
        with self.assertRaises(SurveyError):
            submit_reward.pick_number(A, name, 7, self.r)                  # da quay
        ov = results_service.overview(HR, name, repo=self.r)
        self.assertEqual(ov["reward"]["empty_numbers"], ["002"])
        with self.assertRaises(SurveyError):
            draw_service.draw_now(HR, name, self.r)

    def test_race_everyone_who_submitted_gets_a_cart(self):
        name = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(30)},
                         prizes=[{"label": "Bánh", "quantity": 2}])
        for c in (CC, A, B):
            respond_service.submit(c, name, ok(c), repo=self.r)
        with self.assertRaises(SurveyPermissionError):
            draw_service.draw_now(A, name, self.r)
        draw_service.draw_now(HR, name, self.r)
        data = json.loads(self.r.surveys[name]["draw_results"])
        self.assertEqual(data["order"], ["a@x", "b@x", "c@x"])
        self.assertEqual([(w["place"], w["user"]) for w in data["winners"]], [(1, "a@x"), (2, "b@x")])
        self.assertEqual(self.r.parts[(name, "c@x")]["reward_result"], "Lose")

    def test_home_feed_timeline(self):
        name = self.make(settings={"reward_mode": "lucky_number", "draw_scheduled_at": self.at(60),
                                   "audience_mode": "custom"},
                         targets=[{"kind": "Department", "department": "Ops"}],
                         prizes=[{"label": "Trà sữa", "quantity": 1}])
        later = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(60 * 24 * 3)},
                          prizes=[{"label": "Bánh", "quantity": 1}])
        self.assertTrue(draw_feed.any_soon(self.r))
        f = draw_feed.for_user("a@x", self.r)
        self.assertEqual(f["draws"], [])
        self.assertEqual([(u["name"], u["me"], u["days_left"]) for u in f["upcoming"]],
                         [(name, "not_submitted", 0), (later, "not_submitted", 3)])
        self.assertEqual(f["timers"], [{"name": name, "open_at": "2026-10-01 09:55:00", "draw_at": "2026-10-01 10:00:00"}])
        self.assertEqual([u["name"] for u in draw_feed.for_user("c@x", self.r)["upcoming"]], [later])  # ngoai doi tuong
        respond_service.submit(A, name, ok(A), repo=self.r)
        submit_reward.pick_number(A, name, 27, self.r)
        self.assertEqual(draw_feed.for_user("a@x", self.r)["upcoming"][0]["my_number"], "027")
        self.r.clock = NOW + datetime.timedelta(minutes=57)
        d = draw_feed.for_user("a@x", self.r)["draws"][0]
        self.assertEqual((d["state"], d["my_number"], d["holders"], d["results"]), ("countdown", "027", 1, []))
        self.r.clock = NOW + datetime.timedelta(minutes=60, seconds=20)
        self.assertEqual(draw_feed.for_user("a@x", self.r)["draws"][0]["state"], "live")   # job chua chay
        draw_service.tick(self.r)
        d = draw_feed.for_user("a@x", self.r)["draws"][0]
        self.assertEqual(d["state"], "live")
        self.assertEqual(len(d["results"]), 1)
        self.r.clock = NOW + datetime.timedelta(hours=5)
        d = draw_feed.for_user("a@x", self.r)["draws"][0]
        self.assertEqual(d["state"], "done")
        self.assertEqual(d["results"][0]["number"], "001")
        self.r.clock = NOW + datetime.timedelta(days=1)
        self.assertEqual([u["name"] for u in draw_feed.for_user("a@x", self.r)["upcoming"]], [later])

    def test_manual_early_draw_shows_today_only(self):
        name = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(60 * 26)},
                         prizes=[{"label": "Bánh", "quantity": 1}])
        respond_service.submit(A, name, ok(A), repo=self.r)
        draw_service.draw_now(HR, name, self.r)
        f = draw_feed.for_user("a@x", self.r)
        self.assertEqual([(d["name"], d["state"]) for d in f["draws"]], [(name, "live")])
        self.assertEqual(f["upcoming"], [])
        self.assertEqual(f["draws"][0]["results"][0]["is_me"], True)
        self.r.clock = NOW + datetime.timedelta(hours=1)
        self.assertEqual(draw_feed.for_user("a@x", self.r)["draws"][0]["state"], "done")
        self.r.clock = NOW + datetime.timedelta(hours=27)               # hom sau = ngay hen: van hien ket qua
        self.assertEqual(len(draw_feed.for_user("a@x", self.r)["draws"]), 1)
        self.r.clock = NOW + datetime.timedelta(days=3)
        self.assertEqual(draw_feed.for_user("a@x", self.r)["draws"], [])

    def test_wheel_hides_position_before_spin(self):
        """Biet "minh la luot X, dot nay con qua" truoc khi quay = canh duoc luc quay (review 01/10)."""
        name = self.make(settings={"reward_mode": "wheel"}, prizes=[{"label": "Nước", "quantity": 2}])
        res = respond_service.submit(A, name, ok(A), repo=self.r)
        self.assertIsNone(res["reward"]["waves"])
        self.assertIsNone(respond_service.get_form(A, name, repo=self.r)["reward"]["waves"])
        self.assertEqual(submit_reward.spin(A, name, self.r)["waves"]["seq"], 1)

    def test_anonymous_board_and_race_hide_names(self):
        name = self.make(settings={"reward_mode": "lucky_number", "anonymous": 1, "draw_scheduled_at": self.at(60)},
                         prizes=[{"label": "Nước", "quantity": 1}])
        for c, n in ((A, 5), (B, 9)):
            respond_service.submit(c, name, ok(c), repo=self.r)
            submit_reward.pick_number(c, name, n, self.r)
        board = submit_reward.board(A, name, self.r)
        self.assertEqual([(h["label"], h["name"], h["me"]) for h in board["holders"]], [("005", "", True), ("009", "", False)])
        race = self.make(settings={"reward_mode": "race", "anonymous": 1, "draw_scheduled_at": self.at(60)},
                         prizes=[{"label": "Bánh", "quantity": 1}])
        for c in (A, B, CC):
            respond_service.submit(c, race, ok(c), repo=self.r)
        draw_service.draw_now(HR, race, self.r)
        d = draw_feed.one("c@x", race, self.r)
        self.assertEqual([(r["place"], r["name"], r["is_me"]) for r in d["racers"]],
                         [(1, "A", False), (2, "", False), (3, "C", True)])

    def test_reschedule_after_alert_alerts_again(self):
        name = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(60)},
                         prizes=[{"label": "Bánh", "quantity": 1}])
        self.r.clock = NOW + datetime.timedelta(minutes=56)
        draw_service.tick(self.r)
        draw_service.notify_soon(name, repo=self.r)
        got = builder_service.get(HR, name, repo=self.r)
        builder_service.save(HR, name, json.dumps({"settings": dict(got["settings"], draw_scheduled_at=self.at(180)),
                                                   "prizes": got["prizes"], "targets": [], "modified": got["modified"]}), repo=self.r)
        self.assertIsNone(self.r.surveys[name]["draw_notified_at"])
        self.r.clock = NOW + datetime.timedelta(minutes=176)
        self.assertEqual(draw_service.tick(self.r)["notified"], 1)
        draw_service.notify_soon(name, repo=self.r)
        keys = [n[3] for n in self.r.notified if n[0] == "a@x" and "|draw_soon|" in n[3]]
        self.assertEqual(len(set(keys)), 2)                        # khoa chong trung mang gio hen

    def test_one_draw_endpoint_is_cheap_until_drawn(self):
        name = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(60), "audience_mode": "custom"},
                         targets=[{"kind": "Department", "department": "Ops"}], prizes=[{"label": "Bánh", "quantity": 1}])
        self.r.employees = lambda: (_ for _ in ()).throw(AssertionError("khong duoc tinh doi tuong"))
        self.assertEqual(draw_feed.one("c@x", name, self.r), {"name": name, "drawn": False, "results": []})
        del self.r.employees
        draw_service.draw_now(HR, name, self.r)                   # 0 xe: van la da chot
        d = draw_feed.one("a@x", name, self.r)
        self.assertEqual((d["drawn"], d["results"], d["racer_total"]), (True, [], 0))
        self.assertIsNone(draw_feed.one("c@x", name, self.r))      # ngoai doi tuong

    def test_cannot_change_draw_after_drawn(self):
        name = self.make(settings={"reward_mode": "race", "draw_scheduled_at": self.at(30)},
                         prizes=[{"label": "Bánh", "quantity": 1}])
        draw_service.draw_now(HR, name, self.r)
        got = builder_service.get(HR, name, repo=self.r)
        st = dict(got["settings"], draw_scheduled_at=self.at(90))
        with self.assertRaises(SurveyError):
            builder_service.save(HR, name, json.dumps({"settings": st, "prizes": got["prizes"], "targets": [],
                                                       "modified": got["modified"]}), repo=self.r)


class TestResults(Base):
    def test_overview_participation_export(self):
        name = self.make()
        respond_service.submit(A, name, {"q1": {"sel": ["y"]}, "q2": "Tốt"}, repo=self.r)
        respond_service.submit(B, name, {"q1": {"sel": ["n"]}}, repo=self.r)
        ov = results_service.overview(HR, name, repo=self.r)
        self.assertEqual((ov["eligible"], ov["submitted"]), (4, 2))
        self.assertEqual(ov["summary"]["questions"]["q1"]["counts"], {"y": 1, "n": 1})
        people = results_service.participation(HR, name, repo=self.r)["people"]
        self.assertEqual([p["done"] for p in people], [False, False, True, True])
        fname, rows = results_service.export(HR, name, repo=self.r)
        self.assertEqual(rows[0][:3], ["Thời gian nộp", "Người trả lời", "Email"])
        self.assertIn("Có", rows[1] + rows[2])
        self.assertEqual(results_service.response_at(HR, name, 0, repo=self.r)["respondent"], "B")
        with self.assertRaises(SurveyPermissionError):
            results_service.overview(A, name, repo=self.r)


if __name__ == "__main__":
    unittest.main()
