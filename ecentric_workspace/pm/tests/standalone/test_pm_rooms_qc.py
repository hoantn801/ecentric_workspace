# -*- coding: utf-8 -*-
"""Phòng họp - QC 05/11/2026: lỗi thật tìm được khi kiểm thử, mỗi lỗi một test tái hiện.

Graph giả (kế thừa test_pm_rooms.Graph) giống Graph thật hơn ở chỗ test cần:
  * $batch tối đa 20 request (Graph trả 400 cả lô nếu hơn),
  * calendarView phân trang theo $top + @odata.nextLink,
  * /instances của một chuỗi."""
import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pm_rooms import Base, Graph, _Resp, gev, ME, DAY  # noqa: E402


def at(day, h0, h1, eid, org="bob@ec.vn", name="Bob", **kw):
    e = gev(eid, h0, h1, org=org, name=name, **kw)
    e["start"] = {"dateTime": "%sT%s:00.0000000" % (day, h0)}
    e["end"] = {"dateTime": "%sT%s:00.0000000" % (day, h1)}
    return e


def plus(day, n):
    return str(datetime.date.fromisoformat(day) + datetime.timedelta(days=n))


class StrictGraph(Graph):
    def __init__(self):
        Graph.__init__(self)
        self.instances = {}        # series master id -> [{"iCalUId", "start", "end"}]
        self.get_raises = None

    @staticmethod
    def _win(url):
        q = url.split("?", 1)[1] if "?" in url else ""
        p = dict(x.split("=", 1) for x in q.split("&") if "=" in x)
        lo = p.get("startDateTime", "").replace("%2B07:00", "").replace("T", " ")
        hi = p.get("endDateTime", "").replace("%2B07:00", "").replace("T", " ")
        return lo, hi, int(p.get("$top") or 10), int(p.get("$skip") or 0)

    def _page(self, base, url, evs):
        lo, hi, top, skip = self._win(url)
        evs = [e for e in evs if (not lo or e["end"]["dateTime"][:19].replace("T", " ") > lo)
               and (not hi or e["start"]["dateTime"][:19].replace("T", " ") < hi)]
        body = {"value": evs[skip:skip + top]}
        if skip + top < len(evs):
            nxt = url.split("&$skip=")[0] + "&$skip=%d" % (skip + top)
            body["@odata.nextLink"] = (base + nxt) if nxt.startswith("/") else nxt
        return body

    def post(self, url, json=None, headers=None, timeout=None, **k):
        if url.endswith("/$batch"):
            self.calls.append(("POST", url, json))
            if len(json["requests"]) > 20:
                return _Resp(400, {"error": {"code": "BadRequest", "message": "max 20"}})
            out = []
            for r in json["requests"]:
                em = r["url"].split("/users/")[1].split("/")[0].replace("%40", "@")
                if em in self.room_cal:
                    out.append({"id": r["id"], "status": 200,
                                "body": self._page("https://graph.microsoft.com/v1.0", r["url"], self.room_cal[em])})
                else:
                    out.append({"id": r["id"], "status": 404, "body": {"error": {"code": "ErrorItemNotFound"}}})
            return _Resp(200, {"responses": out})
        return Graph.post(self, url, json=json, headers=headers, timeout=timeout, **k)

    def get(self, url, headers=None, timeout=None, **k):
        if self.get_raises:
            raise self.get_raises
        if "/instances" in url:
            self.calls.append(("GET", url))
            eid = url.split("/events/")[1].split("/instances")[0]
            return _Resp(200, self._page("", url, self.instances.get(eid, [])))
        if "/calendarView" in url and "/users/alice" not in url:
            self.calls.append(("GET", url))
            em = url.split("/users/")[1].split("/")[0].replace("%40", "@")
            return _Resp(200, self._page("", url, self.room_cal.get(em, [])))
        if "/calendarView" in url:
            self.calls.append(("GET", url))
            return _Resp(200, self._page("", url, list(self.my_events.values())))
        return Graph.get(self, url, headers=headers, timeout=timeout, **k)


class QC(Base):
    def setUp(self):
        Base.setUp(self)
        g = StrictGraph()
        g.room_cal = self.g.room_cal
        self.g = g
        req = sys.modules["requests"]
        req.get, req.post, req.patch = g.get, g.post, g.patch

    def created(self):
        return [c[2] for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")]

    def patches(self):
        return [c[2] for c in self.g.calls if c[0] == "PATCH"]


class TestGraphLimits(QC):
    def test_more_than_20_rooms_are_split_into_batches(self):
        for i in range(22):
            em = "room.x%d@ecentric.vn" % i
            self.fk.add("EC Meeting Room", name="9.%d" % i, room_code="9.%d" % i, room_title="X%d" % i, email=em,
                        floor="", note="", capacity=None, sort_order=100 + i, enabled=1)
            self.g.room_cal[em] = []
        out = self.r.day()
        self.assertEqual(len(out["rooms"]), 25)
        self.assertFalse([x["code"] for x in out["rooms"] if x.get("error")])
        self.assertTrue(all(len(c[2]["requests"]) <= 20 for c in self.g.batches()))

    def test_busy_room_beyond_first_page_is_still_a_clash(self):
        # a room with 230 events over the next months: the clash is on the 230th (page 2)
        evs = [at(plus(DAY, 1 + i // 4), "%02d:00" % (8 + i % 4), "%02d:00" % (9 + i % 4), "p%d" % i)
               for i in range(229)]
        evs.append(at(plus(DAY, 60), "14:30", "15:30", "late"))
        self.g.room_cal["room.tho@ecentric.vn"] = evs
        last = evs[-1]["start"]["dateTime"][:10]
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 14:00:00", DAY + " 15:00:00", "Giao ban", repeat="daily", repeat_until=last)
        self.assertIn(last[8:10] + "/" + last[5:7], str(cm.exception))
        self.assertFalse(self.created())

    def test_mine_follows_next_link(self):
        for i in range(205):
            self.g.my_events["N%d" % i] = {"id": "N%d" % i, "subject": "x", "isOrganizer": True, "attendees": [],
                                           "start": {"dateTime": plus(DAY, 1) + "T08:00:00"},
                                           "end": {"dateTime": plus(DAY, 1) + "T08:30:00"}}
        eid = self.r.book("5.1", plus(DAY, 2) + " 15:00:00", plus(DAY, 2) + " 16:00:00", "Giao ban")["event_id"]
        self.assertEqual([x["event_id"] for x in self.r.mine()["rows"]], [eid])

    def test_read_timeout_on_own_event_is_friendly_not_500(self):
        eid = self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Giao ban")["event_id"]
        self.g.get_raises = RuntimeError("ReadTimeout")
        for fn in (lambda: self.r.cancel(eid), lambda: self.r.update(eid, subject="x"),
                   lambda: self.r.booking_state(eid)):
            with self.assertRaises(self.fk.module.ValidationError) as cm:
                fn()
            self.assertIn("Microsoft 365", str(cm.exception))

    def test_mine_bad_days_param_does_not_500(self):
        self.assertEqual(self.r.mine(days="abc")["rows"], [])


class TestBookingWindow(QC):
    """BookingWindowInDays=180 tính từ HÔM NAY (Exchange), không phải từ buổi đầu của chuỗi."""

    def test_series_ending_beyond_today_plus_180_refused(self):
        start = plus(DAY, 30)
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", start + " 09:00:00", start + " 10:00:00", "Hop", repeat="weekly",
                        repeat_until=plus(DAY, 200))
        self.assertIn("180", str(cm.exception))
        self.assertTrue(self.r.book("1.2", start + " 09:00:00", start + " 10:00:00", "Hop", repeat="weekly",
                                    repeat_until=plus(DAY, 180))["ok"])

    def test_single_booking_beyond_window_refused(self):
        d = plus(DAY, 190)
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", d + " 09:00:00", d + " 10:00:00", "Hop")
        self.assertIn("180", str(cm.exception))
        self.assertFalse(self.created())

    def test_daily_series_every_occurrence_checked_not_cut_at_130(self):
        last = plus(DAY, 180)
        day170 = plus(DAY, 170)
        self.g.room_cal["room.tho@ecentric.vn"] = [at(day170, "15:30", "16:30", "late")]
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", repeat="daily", repeat_until=last)
        self.assertIn(day170[8:10] + "/" + day170[5:7], str(cm.exception))
        self.assertEqual(len(self.r._occurrences(DAY + " 15:00:00", DAY + " 16:00:00",
                                                 self.r._recurrence("daily", last, DAY + " 15:00:00"))), 181)

    def test_monthly_on_31st_falls_on_last_day_of_short_months(self):
        # Outlook: "Some months have fewer than 31 days... the occurrence will fall on the last day of the month"
        rec = self.r._recurrence("monthly", "2027-03-31", "2026-10-31 09:00:00")
        days = [x[0][:10] for x in self.r._occurrences("2026-10-31 09:00:00", "2026-10-31 10:00:00", rec)]
        self.assertEqual(days, ["2026-10-31", "2026-11-30", "2026-12-31", "2027-01-31", "2027-02-28", "2027-03-31"])

    def test_biweekly_across_new_year(self):
        rec = self.r._recurrence("biweekly", "2027-01-31", "2026-12-21 09:00:00")   # Monday
        days = [x[0][:10] for x in self.r._occurrences("2026-12-21 09:00:00", "2026-12-21 10:00:00", rec)]
        self.assertEqual(days, ["2026-12-21", "2027-01-04", "2027-01-18"])


class TestSeriesEdit(QC):
    def series(self, rng, n=6, room="room.tho@ecentric.vn"):
        """A weekly series made in Teams (range noEnd / numbered): master + n instances."""
        mid = "M1"
        first = DAY
        self.g.my_events[mid] = {
            "id": mid, "iCalUId": "uid-M1", "subject": "Giao ban Teams", "isOrganizer": True, "isCancelled": False,
            "type": "seriesMaster", "start": {"dateTime": first + "T09:00:00.0000000"},
            "end": {"dateTime": first + "T10:00:00.0000000"},
            "attendees": [{"emailAddress": {"address": room}, "type": "resource", "status": {"response": "accepted"}}],
            "recurrence": {"pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["friday"], "firstDayOfWeek": "sunday"},
                           "range": rng}}
        insts = []
        for i in range(n):
            d = plus(first, 7 * i)
            insts.append({"id": "O%d" % i, "iCalUId": "uid-O%d" % i, "start": {"dateTime": d + "T09:00:00.0000000"},
                          "end": {"dateTime": d + "T10:00:00.0000000"}})
            self.g.my_events["O%d" % i] = dict(self.g.my_events[mid], id="O%d" % i, iCalUId="uid-O%d" % i,
                                               type="occurrence", seriesMasterId=mid, recurrence=None,
                                               start=insts[-1]["start"], end=insts[-1]["end"])
        self.g.instances[mid] = insts
        self.g.room_cal[room] = [at(x["start"]["dateTime"][:10], "09:00", "10:00", x["id"], org=ME, name="Alice",
                                    iCalUId=x["iCalUId"]) for x in insts]
        return mid

    def test_teams_series_without_end_date_is_checked_when_time_changes(self):
        self.series({"type": "noEnd", "startDate": DAY, "endDate": "0001-01-01"})
        self.g.room_cal["room.tho@ecentric.vn"].append(at(plus(DAY, 21), "10:00", "11:00", "z", name="Vu"))
        with self.assertRaises(Exception) as cm:
            self.r.update("O1", start=plus(DAY, 7) + " 09:30:00", end=plus(DAY, 7) + " 10:30:00", scope="series")
        self.assertIn(plus(DAY, 21)[8:10] + "/" + plus(DAY, 21)[5:7], str(cm.exception))
        self.assertFalse(self.patches())

    def test_numbered_series_room_change_checks_each_instance(self):
        self.series({"type": "numbered", "startDate": DAY, "endDate": "0001-01-01", "numberOfOccurrences": 6})
        self.g.room_cal["room.phong@ecentric.vn"] = [at(plus(DAY, 35), "09:00", "09:30", "z", name="Vu")]
        with self.assertRaises(Exception) as cm:
            self.r.update("O0", room="5.1", scope="series")
        self.assertIn(plus(DAY, 35)[8:10] + "/" + plus(DAY, 35)[5:7], str(cm.exception))
        self.g.room_cal["room.phong@ecentric.vn"] = []
        self.r.update("O0", room="5.1", scope="series")
        self.assertEqual(self.patches()[-1]["location"]["locationEmailAddress"], "room.phong@ecentric.vn")

    def test_series_time_change_ignores_own_instances_in_same_room(self):
        self.series({"type": "endDate", "startDate": DAY, "endDate": plus(DAY, 35)})
        out = self.r.update("O2", start=plus(DAY, 14) + " 09:30:00", end=plus(DAY, 14) + " 10:30:00", scope="series")
        p = self.patches()[-1]
        self.assertEqual((p["start"]["dateTime"], p["end"]["dateTime"]), (DAY + "T09:30:00", DAY + "T10:30:00"))
        self.assertEqual(out["state"], "pending")

    def test_master_id_with_scope_occurrence_is_the_whole_series(self):
        # FE: dòng "chờ phòng nhận" của chuỗi vừa đặt mang id của seriesMaster
        mid = self.series({"type": "endDate", "startDate": DAY, "endDate": plus(DAY, 35)})
        self.g.room_cal["room.tho@ecentric.vn"].append(at(plus(DAY, 28), "10:00", "11:00", "z", name="Vu"))
        with self.assertRaises(Exception) as cm:
            self.r.update(mid, start=DAY + " 09:30:00", end=DAY + " 10:30:00", scope="occurrence")
        self.assertIn(plus(DAY, 28)[8:10] + "/" + plus(DAY, 28)[5:7], str(cm.exception))
        self.assertFalse(self.patches())


class TestGuestsAndCache(QC):
    def test_room_mailbox_cannot_be_invited_as_guest(self):
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop",
                        attendees=json.dumps(["Room.Phong@ecentric.vn"]))
        self.assertIn("phòng", str(cm.exception).lower())
        self.assertFalse(self.created())

    def test_external_flag_same_in_book_and_mine(self):
        out = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop",
                          attendees=json.dumps(["web@ec.vn", "x@brand.com", "carol@ec.vn"]))
        g = self.r.mine()["rows"][0]["guests"]
        self.assertEqual(out["external"], len([x for x in g if x["external"]]))

    def test_single_email_string_is_one_guest(self):
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", attendees=json.dumps("x@brand.com"))
        self.assertEqual([a["emailAddress"]["address"] for a in self.created()[0]["attendees"][1:]], ["x@brand.com"])

    def test_tentative_booking_from_teams_is_busy(self):
        self.g.room_cal["room.tho@ecentric.vn"] = [gev("t", "15:00", "16:00", showAs="tentative", name="Khach")]
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 15:30:00", DAY + " 16:30:00", "Hop")

    def test_room_added_without_hook_is_not_shown_free_from_stale_cache(self):
        self.r.day()
        self.fk.add("EC Meeting Room", name="1.1", room_code="1.1", room_title="Hoả", email="room.hoa@ecentric.vn",
                    floor="", note="", capacity=None, sort_order=20, enabled=1)
        self.g.room_cal["room.hoa@ecentric.vn"] = [gev("h", "09:00", "11:00")]
        r = self.room(self.r.day(), "1.1")
        self.assertEqual([b["start"][11:16] for b in r["bookings"]], ["09:00"])


class TestRegression(QC):
    """Điểm soi kỹ đã đúng sẵn: khoá lại bằng test để không hỏng về sau."""

    def test_guest_limit_checked_before_db_lookups(self):
        n = {"q": 0}
        orig = self.fk.module.db.get_value

        def counting(*a, **k):
            if a and a[0] == "User":
                n["q"] += 1
            return orig(*a, **k)
        self.fk.module.db.get_value = counting
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop",
                        attendees=json.dumps(["g%d@brand.com" % i for i in range(3000)]))
        self.assertIn("50", str(cm.exception))
        self.assertLessEqual(n["q"], 50)
        self.assertEqual(len(self.r._clean_attendees(json.dumps(["g%d@brand.com" % i for i in range(50)]), ME)), 50)

    def test_truncated_paging_is_an_error_not_free(self):
        self.r._MAX_PAGES = 1
        self.g.room_cal["room.tho@ecentric.vn"] = [at(DAY, "11:00", "11:30", "p%d" % i) for i in range(450)]
        r = self.room(self.r.day(), "1.2")
        self.assertEqual(r.get("error"), "GRAPH_PAGES")

    def test_day_cache_shared_but_mine_flag_per_caller(self):
        self.g.room_cal["room.phong@ecentric.vn"] = [gev("b", "14:00", "15:00", org=ME, name="Alice")]
        self.assertTrue(self.room(self.r.day(), "5.1")["bookings"][0]["mine"])
        self.fk.set_user("bob@ec.vn")
        self.assertFalse(self.room(self.r.day(), "5.1")["bookings"][0]["mine"])
        self.assertEqual(len(self.g.batches()), 1)

    def test_all_day_and_overnight_events_block_the_day(self):
        self.g.room_cal["room.tho@ecentric.vn"] = [
            gev("ad", "00:00", "00:00", isAllDay=True, start={"dateTime": DAY + "T00:00:00.0000000"},
                end={"dateTime": plus(DAY, 1) + "T00:00:00.0000000"})]
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        self.g.room_cal["room.tho@ecentric.vn"] = [
            gev("on", "22:00", "09:00", start={"dateTime": plus(DAY, -1) + "T22:00:00.0000000"},
                end={"dateTime": DAY + "T11:00:00.0000000"})]
        b = self.room(self.r.day(), "1.2")["bookings"]
        self.assertEqual((b[0]["start"], b[0]["end"]), (plus(DAY, -1) + " 22:00:00", DAY + " 11:00:00"))
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 10:30:00", DAY + " 11:30:00", "Hop")
        self.assertTrue(self.r.book("1.2", DAY + " 11:00:00", DAY + " 11:30:00", "Hop")["ok"])   # liền kề

    def test_event_id_cannot_leave_my_mailbox(self):
        for bad in ("../../bob@ec.vn/events/X", "X?$select=*&a=", "X/cancel"):
            try:
                self.r.cancel(bad)
            except Exception:
                pass
        urls = [c[1] for c in self.g.calls if c[0] in ("GET", "POST") and "/events/" in c[1]]
        self.assertTrue(urls)
        for u in urls:
            self.assertTrue(u.startswith("https://graph.microsoft.com/v1.0/users/alice%40ec.vn/events/"), u)
            eid = u.split("/events/")[1].split("?")[0].split("/cancel")[0]
            self.assertNotIn("/", eid)
            self.assertNotIn("?", eid)

    def test_writes_send_timezone_and_prefer_header(self):
        seen = {}
        orig = self.g.post

        def post(url, json=None, headers=None, timeout=None, **k):
            if url.endswith("/events"):
                seen["h"], seen["b"] = headers, json
            return orig(url, json=json, headers=headers, timeout=timeout, **k)
        sys.modules["requests"].post = post
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        self.assertEqual(seen["h"]["Prefer"], 'outlook.timezone="Asia/Ho_Chi_Minh"')
        self.assertEqual(seen["b"]["start"], {"dateTime": DAY + "T15:00:00", "timeZone": "Asia/Ho_Chi_Minh"})


if __name__ == "__main__":
    unittest.main()
