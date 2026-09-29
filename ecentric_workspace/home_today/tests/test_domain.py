# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - quy tac thuan (khong can bench, khong can frappe).
    python -m pytest ecentric_workspace/home_today/tests/test_domain.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from ecentric_workspace.home_today import constants as C  # noqa: E402
from ecentric_workspace.home_today import domain as D     # noqa: E402

T = dt.date(2026, 9, 29)   # Thu Ba
DEPTS = {"Account - EC": "Account", "Data - EC": "Data"}


def emp(name, full, dob=None, doj=None, dept="Account - EC", des="Account Executive"):
    return {"name": name, "employee_name": full, "department": dept, "designation": des,
            "date_of_birth": dob, "date_of_joining": doj}


class TestBirthdays(unittest.TestCase):
    def test_today_and_next_7_days_only(self):
        es = [emp("E1", "Nguyễn Thu Hà", dt.date(1995, 9, 29)),
              emp("E2", "Phạm Quốc Huy", dt.date(1990, 10, 1)),
              emp("E3", "Vũ Hoàng Nam", dt.date(1988, 10, 6)),      # +7: vao
              emp("E4", "Ngoài Tầm", dt.date(1988, 10, 7)),        # +8: khong
              emp("E5", "Hôm Qua", dt.date(1988, 9, 28)),          # da qua: khong
              emp("E6", "Không Ngày Sinh")]
        today, soon = D.birthdays(es, T, DEPTS)
        self.assertEqual([p["name"] for p in today], ["Nguyễn Thu Hà"])
        self.assertEqual([(p["name"], p["date"], p["weekday"]) for p in soon],
                         [("Phạm Quốc Huy", "01/10", "Thứ Năm"), ("Vũ Hoàng Nam", "06/10", "Thứ Ba")])
        self.assertEqual(today[0]["key"], "bd:E1:2026")
        self.assertEqual(today[0]["role"], "Account Executive · Account")

    def test_never_leaks_birth_year_or_age(self):
        today, soon = D.birthdays([emp("E1", "A B", dt.date(1995, 9, 29)), emp("E2", "C D", dt.date(1990, 10, 1))], T, DEPTS)
        blob = repr(today) + repr(soon)
        for bad in ("1995", "1990", "date_of_birth", "age", "tuổi"):
            self.assertNotIn(bad, blob)

    def test_year_wrap_and_feb29(self):
        today, soon = D.birthdays([emp("E1", "Năm Mới", dt.date(1990, 1, 2))], dt.date(2026, 12, 28), DEPTS)
        self.assertEqual(soon[0]["date"], "02/01")
        today, _ = D.birthdays([emp("E2", "Nhuận", dt.date(1996, 2, 29))], dt.date(2027, 2, 28), DEPTS)
        self.assertEqual(len(today), 1, "29/02 o nam khong nhuan mung vao 28/02")
        today, soon = D.birthdays([emp("E2", "Nhuận", dt.date(1996, 2, 29))], dt.date(2028, 2, 28), DEPTS)
        self.assertEqual((len(today), soon[0]["date"]), (0, "29/02"))

    def test_string_dates_accepted(self):
        today, _ = D.birthdays([emp("E1", "A", "1995-09-29")], T, DEPTS)
        self.assertEqual(len(today), 1)


class TestAnniversary(unittest.TestCase):
    def test_full_years_only_today(self):
        es = [emp("E1", "Hồ Ngọc Trâm", doj=dt.date(2023, 9, 29)),
              emp("E2", "Mới Vào", doj=dt.date(2026, 9, 29)),      # hom nay moi vao: khong
              emp("E3", "Khác Ngày", doj=dt.date(2020, 9, 30))]
        out = D.anniversaries(es, T, DEPTS)
        self.assertEqual([(p["name"], p["years"], p["joined"], p["key"]) for p in out],
                         [("Hồ Ngọc Trâm", 3, "29/09/2023", "ann:E1:2026")])


class TestHolidays(unittest.TestCase):
    def test_skip_weekly_off_merge_runs_and_limit(self):
        rows = [{"holiday_date": dt.date(2026, 10, 4), "description": "Sunday", "weekly_off": 1},
                {"holiday_date": dt.date(2027, 1, 1), "description": "<p>Tết Dương lịch</p>", "weekly_off": 0},
                {"holiday_date": dt.date(2027, 2, 5), "description": "Tết Nguyên đán", "weekly_off": 0},
                {"holiday_date": dt.date(2027, 2, 6), "description": "Tết Nguyên đán", "weekly_off": 0},
                {"holiday_date": dt.date(2027, 2, 8), "description": "Tết Nguyên đán", "weekly_off": 0},
                {"holiday_date": dt.date(2026, 9, 2), "description": "Đã qua", "weekly_off": 0}]
        out = D.holidays(rows, T)
        self.assertEqual([(h["name"], h["days_left"], h["days_off"]) for h in out],
                         [("Tết Dương lịch", 94, 1), ("Tết Nguyên đán", 129, 3)])
        self.assertEqual(out[0]["date_label"], "Thứ Sáu, 01/01/2027")
        self.assertEqual((out[0]["day"], out[0]["month"]), ("01", "TH 1"))


class TestAnnouncements(unittest.TestCase):
    def test_window_tags_poster_links_and_order(self):
        rows = [
            {"name": "A1", "title": "Chấm công trên điện thoại", "category": "Tính năng mới", "published": 1,
             "start_date": dt.date(2026, 9, 29), "summary": "Tóm tắt", "image": "/files/a.png",
             "link": "/ec-hr/attendance", "link_label": "Dùng thử"},
            {"name": "A2", "title": "Hết hạn mặc định", "category": "Thông báo", "published": 1,
             "start_date": dt.date(2026, 9, 1)},                                   # 7 ngay -> het
            {"name": "A3", "title": "Có hạn riêng", "category": "Sự kiện", "published": 1,
             "start_date": dt.date(2026, 9, 1), "end_date": dt.date(2026, 10, 3),
             "content": "<p>Nội <b>dung</b></p>", "image": "/private/files/x.png", "link": "javascript:alert(1)"},
            {"name": "A4", "title": "Hẹn giờ mai", "published": 1, "start_date": dt.date(2026, 9, 30)},
            {"name": "A5", "title": "Nháp", "published": 0, "start_date": dt.date(2026, 9, 29)},
            {"name": "A6", "title": "Poster Trung thu", "category": "Sự kiện", "published": 1,
             "display": "Chỉ ảnh (hiện full)", "start_date": dt.date(2026, 9, 28), "image": "/files/tt.jpg"},
            {"name": "A7", "title": "Chỉ ảnh mà không có ảnh", "published": 1,
             "display": "Chỉ ảnh (hiện full)", "start_date": dt.date(2026, 9, 27)},
            {"name": "A8", "title": "Chính sách", "category": "Chính sách", "published": 1,
             "start_date": dt.date(2026, 9, 23)},                                   # ngay thu 7 -> con
        ]
        out = D.announcements(rows, T)
        self.assertEqual([(n["key"], n["tag"], n["poster"]) for n in out],
                         [("ann:A1", "mod", False), ("ann:A6", "inf", True), ("ann:A7", "inf", False),
                          ("ann:A8", "pol", False), ("ann:A3", "inf", False)])
        a1 = out[0]
        self.assertEqual((a1["url"], a1["link_label"], a1["tag_label"], a1["date_label"]),
                         ("/ec-hr/attendance", "Dùng thử", "Tính năng mới", "29/09/2026"))
        a3 = out[-1]
        self.assertEqual((a3["excerpt"], a3["image"], a3["url"]), ("Nội dung", "", ""),
                         "anh private khong dua len; link javascript: bi bo")
        self.assertEqual(out[1]["image"], "/files/tt.jpg")

    def test_link_whitelist(self):
        for bad in ("javascript:alert(1)", "//evil.com/x", "data:text/html,x", " "):
            self.assertEqual(D._safe_link(bad), "", bad)
        for ok in ("/pm", "https://team.ecentric.vn/x", "http://a.b"):
            self.assertEqual(D._safe_link(ok), ok)


class TestCelebration(unittest.TestCase):
    BD = [{"emp": "E1", "name": "Nguyễn Thu Hà", "department": "Account - EC"},
          {"emp": "E2", "name": "Trần Minh Khoa", "department": "Data - EC"}]

    def test_levels_by_viewer(self):
        self.assertEqual(D.celebration([], {"name": "E1"}, DEPTS)["level"], C.LEVEL_NONE)
        me = D.celebration(self.BD, {"name": "E1", "department": "Account - EC"}, DEPTS)
        self.assertEqual(me["level"], C.LEVEL_ME)
        dept = D.celebration(self.BD, {"name": "E9", "department": "Data - EC"}, DEPTS)
        self.assertEqual((dept["level"], dept["badge"]), (C.LEVEL_DEPT, "Phòng Data có sinh nhật Khoa"))
        other = D.celebration(self.BD, {"name": "E9", "department": "HR - EC"}, DEPTS)
        self.assertEqual((other["level"], other["badge"]), (C.LEVEL_LIGHT, "Hôm nay có 2 sinh nhật"))
        self.assertEqual(D.celebration(self.BD, None, DEPTS)["level"], C.LEVEL_LIGHT, "khong co ho so nhan vien")


class TestReactions(unittest.TestCase):
    def test_counts_names_mine(self):
        rows = [{"target": "bd:E1:2026", "kind": "heart", "user": "a@x"},
                {"target": "bd:E1:2026", "kind": "heart", "user": "me@x"},
                {"target": "bd:E1:2026", "kind": "cake", "user": "b@x"},
                {"target": "rac", "kind": "heart", "user": "a@x"},
                {"target": "bd:E1:2026", "kind": "khong-co", "user": "a@x"}]
        out = D.reactions_view(rows, ["bd:E1:2026"], "me@x", {"a@x": "An", "b@x": "Bình"})
        v = out["bd:E1:2026"]
        self.assertEqual(set(v), set(C.REACTION_KINDS))
        self.assertEqual((v["heart"]["n"], v["heart"]["mine"], v["heart"]["names"]), (2, True, ["An"]))
        self.assertEqual((v["cake"]["n"], v["flower"]["n"]), (1, 0))
        self.assertNotIn("rac", out)


class TestPeople(unittest.TestCase):
    def test_initials_and_stable_color(self):
        self.assertEqual(D.initials("Nguyễn Thu Hà"), "TH")
        self.assertEqual(D.initials(""), "?")
        self.assertEqual(D.color_index("HR-EMP-0001"), D.color_index("HR-EMP-0001"))


if __name__ == "__main__":
    unittest.main()
