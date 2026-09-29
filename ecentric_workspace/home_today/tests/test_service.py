# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - service chay THAT tren repo gia (khong can bench).
    python -m pytest ecentric_workspace/home_today/tests/test_service.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from ecentric_workspace.home_today import service as S  # noqa: E402

NOW = dt.datetime(2026, 9, 29, 9, 15)


class Dup(Exception):
    pass


class FakeRepo:
    def __init__(self):
        self.cache = {}
        self.emps = [
            {"name": "E1", "employee_name": "Nguyễn Thu Hà", "user_id": "ha@x", "department": "Account - EC",
             "designation": "AE", "date_of_birth": dt.date(1995, 9, 29), "date_of_joining": dt.date(2022, 1, 5)},
            {"name": "E2", "employee_name": "Trần Minh Khoa", "user_id": "khoa@x", "department": "Data - EC",
             "designation": "DA", "date_of_birth": dt.date(1993, 10, 2), "date_of_joining": dt.date(2023, 9, 29)},
            {"name": "E3", "employee_name": "Lê Văn Xem", "user_id": "xem@x", "department": "Account - EC",
             "designation": "KAM", "date_of_birth": None, "date_of_joining": None},
        ]
        self.rx = []
        self.onboard = [{"name": "EC-NSP-0001", "candidate_name": "Lê Bảo Ngọc", "position": "Content",
                         "department": "Marketing", "welcome_intro": "Xin chào"}]
        self.calls = {"employees": 0, "onboard": 0}
        self.fail = None

    # doc
    def now(self): return NOW
    def cache_get(self, k): return self.cache.get(k)
    def cache_set(self, k, v, ttl): self.cache[k] = v
    def department_names(self): return {"Account - EC": "Account", "Data - EC": "Data"}

    def active_employees(self):
        self.calls["employees"] += 1
        if self.fail:
            raise self.fail
        return self.emps

    def viewer_employee(self, user):
        e = next((e for e in self.emps if e["user_id"] == user), None)
        return e and {"name": e["name"], "department": e["department"], "company": "EC", "holiday_list": "HL"}

    def holiday_list_for(self, viewer): return "HL"
    def holidays(self, hl, today, days): return [{"holiday_date": dt.date(2027, 1, 1), "description": "Tết Dương lịch"}]
    def news_rows(self, today): return []
    def policy_rows(self, today): return []

    def onboard_rows(self):
        self.calls["onboard"] += 1
        return self.onboard

    def reactions(self, targets): return [r for r in self.rx if r["target"] in targets]
    def full_names(self, users): return {"xem@x": "Lê Văn Xem"}
    def find_reaction(self, t, k, u): return next((i for i, r in enumerate(self.rx) if (r["target"], r["kind"], r["user"]) == (t, k, u)), None) if any((r["target"], r["kind"], r["user"]) == (t, k, u) for r in self.rx) else None
    def remove_reaction(self, i): self.rx.pop(i)
    def add_reaction(self, t, k, u, d): self.rx.append({"target": t, "kind": k, "user": u})
    def is_duplicate(self, exc): return isinstance(exc, Dup)
    def log_error(self, title): self.logged = title


class TestToday(unittest.TestCase):
    def test_payload_for_a_colleague(self):
        r = FakeRepo()
        out = S.today("xem@x", repo=r)
        self.assertTrue(out["has_content"])
        self.assertEqual(out["date_label"], "Thứ Ba, 29/09/2026")
        self.assertEqual([p["name"] for p in out["birthdays"]["today"]], ["Nguyễn Thu Hà"])
        self.assertEqual([(p["name"], p["date"]) for p in out["birthdays"]["soon"]], [("Trần Minh Khoa", "02/10")])
        self.assertEqual([(p["name"], p["years"]) for p in out["anniversaries"]], [("Trần Minh Khoa", 3)])
        self.assertEqual(out["onboard"][0]["key"], "new:EC-NSP-0001")
        self.assertEqual(out["holidays"][0]["name"], "Tết Dương lịch")
        self.assertTrue(out["event_coming_soon"])
        self.assertEqual(set(out["reactions"]), {"bd:E1:2026", "new:EC-NSP-0001", "ann:E2:2026"})
        self.assertEqual(set(out["keys"]), {"bd:E1:2026", "new:EC-NSP-0001", "ann:E2:2026"})

    def test_no_ids_or_birth_year_leave_the_server(self):
        blob = repr(S.today("xem@x", repo=FakeRepo()))
        for bad in ("1995", "1993", "'emp'", "Account - EC", "date_of_birth", "user_id", "ha@x"):
            self.assertNotIn(bad, blob)

    def test_guest_gets_nothing(self):
        r = FakeRepo()
        self.assertEqual(S.today("Guest", repo=r), {"has_content": False})
        self.assertEqual(r.calls["employees"], 0)

    def test_shared_part_cached_per_day(self):
        r = FakeRepo()
        S.today("xem@x", repo=r)
        S.today("ha@x", repo=r)
        self.assertEqual(r.calls["employees"], 1)


class TestToggle(unittest.TestCase):
    def test_on_off_and_counts(self):
        r = FakeRepo()
        a = S.toggle("xem@x", "bd:E1:2026", "heart", repo=r)
        self.assertEqual((a["reactions"]["heart"]["n"], a["reactions"]["heart"]["mine"]), (1, True))
        b = S.toggle("xem@x", "bd:E1:2026", "heart", repo=r)
        self.assertEqual(b["reactions"]["heart"]["n"], 0)
        self.assertEqual(r.rx, [])

    def test_rejects_bad_kind_target_and_guest(self):
        r = FakeRepo()
        for args in (("xem@x", "bd:E1:2026", "poop"), ("xem@x", "bd:E2:2026", "heart"),
                     ("xem@x", "bd:E1:2025", "heart"), ("xem@x", "news:N1", "heart"), ("Guest", "bd:E1:2026", "heart")):
            with self.assertRaises(S.HomeTodayError, msg=args):
                S.toggle(*args, repo=r)
        self.assertEqual(r.rx, [])

    def test_double_click_race_is_not_an_error(self):
        r = FakeRepo()

        def boom(*a):
            raise Dup()
        r.add_reaction = boom
        out = S.toggle("xem@x", "new:EC-NSP-0001", "party", repo=r)
        self.assertEqual(out["target"], "new:EC-NSP-0001")

    def test_other_errors_propagate(self):
        r = FakeRepo()

        def boom(*a):
            raise RuntimeError("db down")
        r.add_reaction = boom
        with self.assertRaises(RuntimeError):
            S.toggle("xem@x", "bd:E1:2026", "cake", repo=r)


class TestCelebration(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(S.celebration("ha@x", repo=FakeRepo())["level"], 3)
        self.assertEqual(S.celebration("xem@x", repo=FakeRepo())["level"], 2)
        self.assertEqual(S.celebration("khoa@x", repo=FakeRepo())["level"], 1)
        self.assertEqual(S.celebration("Guest", repo=FakeRepo())["level"], 0)

    def test_never_raises(self):
        r = FakeRepo()
        r.fail = RuntimeError("db down")
        out = S.celebration("xem@x", repo=r)
        self.assertEqual(out, {"level": 0, "badge": "", "has_content": False})
        self.assertEqual(r.logged, "home_today.celebration")

    def test_has_content_without_birthdays(self):
        r = FakeRepo()
        r.emps = [dict(r.emps[2])]
        r.onboard = []
        self.assertEqual(S.celebration("xem@x", repo=r), {"level": 0, "badge": "", "has_content": False})
        r2 = FakeRepo()
        r2.emps = [dict(r2.emps[2])]
        self.assertTrue(S.celebration("xem@x", repo=r2)["has_content"], "chi co ban moi cung la co noi dung")


if __name__ == "__main__":
    unittest.main()
