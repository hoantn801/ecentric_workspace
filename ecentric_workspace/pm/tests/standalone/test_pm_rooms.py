# -*- coding: utf-8 -*-
"""Phòng họp (05/11/2026) - pm.api.rooms with a fake Graph (no network, no bench).

Covers: one $batch read for all rooms, Teams bookings show as busy, "mine" by organiser,
room not created yet / sync off degrade (never 500), 60 s cache + invalidation after booking,
book() re-checks the room and refuses a clash, creates the event on the CALLER's calendar with
the room as resource + Teams link, booking_state from the room's answer, cancel organiser-only,
input guards (past, > 10 h, end <= start, bad guests)."""
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake  # noqa: E402

ME = "alice@ec.vn"
DAY = "2026-10-16"      # _pm_fake.TODAY
ROOMS = [("5.1", "Phong", "room.phong@ecentric.vn", 10), ("1.2", "Thổ", "room.tho@ecentric.vn", 30),
         ("5.2", "Cabin", "room.cabin@ecentric.vn", 50)]


class _Resp(object):
    def __init__(self, code, body=None):
        self.status_code = code
        self._b = body if body is not None else {}

    def json(self):
        return self._b


def gev(eid, h0, h1, org="bob@ec.vn", name="Bob", **kw):
    e = {"id": eid, "iCalUId": "uid-" + eid, "subject": name, "showAs": "busy", "isCancelled": False,
         "isAllDay": False, "start": {"dateTime": "%sT%s:00.0000000" % (DAY, h0)},
         "end": {"dateTime": "%sT%s:00.0000000" % (DAY, h1)},
         "organizer": {"emailAddress": {"address": org, "name": name}}}
    e.update(kw)
    return e


class Graph(object):
    def __init__(self):
        self.room_cal = {}          # room email -> [events]   (missing key -> 404)
        self.my_events = {}         # id -> event (caller calendar)
        self.calls = []
        self.batch_status = 200
        self.create_status = 201

    def patch(self, url, json=None, headers=None, timeout=None, **k):
        self.calls.append(("PATCH", url, json))
        eid = url.split("/events/")[1].split("?")[0]
        ev = self.my_events.get(eid)
        if not ev:
            return _Resp(404)
        for k2, v in json.items():
            if k2 == "attendees":
                v = [dict(a, status={"response": "none"}) for a in v]
            if k2 in ("start", "end"):
                v = {"dateTime": v["dateTime"] + ".0000000"}
            ev[k2] = v
        return _Resp(200, ev)

    def get(self, url, headers=None, timeout=None, **k):
        self.calls.append(("GET", url))
        if "/instances" in url:
            return _Resp(200, {"value": []})
        if "/calendarView" in url:
            return _Resp(200, {"value": list(self.my_events.values())})
        eid = url.split("/events/")[1].split("?")[0]
        ev = self.my_events.get(eid.replace("%3D", "="))
        return _Resp(200, ev) if ev else _Resp(404, {"error": {"code": "ErrorItemNotFound"}})

    def post(self, url, json=None, headers=None, timeout=None, **k):
        self.calls.append(("POST", url, json))
        if url.endswith("/$batch"):
            if self.batch_status != 200:
                return _Resp(self.batch_status)
            out = []
            for r in json["requests"]:
                em = r["url"].split("/users/")[1].split("/")[0].replace("%40", "@")
                if em in self.room_cal:
                    out.append({"id": r["id"], "status": 200, "body": {"value": self.room_cal[em]}})
                else:
                    out.append({"id": r["id"], "status": 404, "body": {"error": {"code": "ErrorItemNotFound"}}})
            return _Resp(200, {"responses": out})
        if url.endswith("/cancel"):
            eid = url.split("/events/")[1].split("/cancel")[0]
            self.my_events[eid]["isCancelled"] = True
            return _Resp(202)
        if url.endswith("/events"):
            if self.create_status not in (200, 201):
                return _Resp(self.create_status, {"error": {"code": "ErrorAccessDenied"}})
            eid = "EV%d" % (len(self.my_events) + 1)
            ev = dict(json, id=eid, iCalUId="uid-" + eid, isOrganizer=True, isCancelled=False,
                      type="seriesMaster" if json.get("recurrence") else "singleInstance",
                      onlineMeeting={"joinUrl": "https://teams/x"} if json.get("isOnlineMeeting") else None)
            ev["attendees"] = [dict(a, status={"response": "none"}) for a in json["attendees"]]
            ev["start"] = {"dateTime": json["start"]["dateTime"] + ".0000000"}
            ev["end"] = {"dateTime": json["end"]["dateTime"] + ".0000000"}
            self.my_events[eid] = ev
            return _Resp(201, ev)
        return _Resp(400)

    def batches(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith("/$batch")]


class Base(unittest.TestCase):
    def setUp(self, sync=1):
        fk = _pm_fake.install()
        fk.module.get_conf = lambda: {"ec_pm_calendar_sync": sync}
        perm = types.ModuleType("ecentric_workspace.pm.permissions")
        perm.require_pm_access = lambda *a, **k: None
        g = types.ModuleType("ecentric_workspace.notification_center.providers.graph")
        g.is_configured = lambda *a: True
        g.get_app_token = lambda *a: (True, "tok")
        self.g = Graph()
        req = types.ModuleType("requests")
        req.get, req.post, req.patch = self.g.get, self.g.post, self.g.patch
        sys.modules.update({"ecentric_workspace.pm.permissions": perm,
                            "ecentric_workspace.notification_center": types.ModuleType("x"),
                            "ecentric_workspace.notification_center.providers": types.ModuleType("y"),
                            "ecentric_workspace.notification_center.providers.graph": g,
                            "requests": req})
        sys.modules["ecentric_workspace.notification_center.providers"].graph = g
        for code, title, email, sort in ROOMS:
            fk.add("EC Meeting Room", name=code, room_code=code, room_title=title, email=email,
                   floor="", note="", capacity=None, sort_order=sort, enabled=1)
            self.g.room_cal[email] = []
        fk.add("User", name="carol@ec.vn", enabled=1, user_type="System User")
        fk.add("User", name="web@ec.vn", enabled=1, user_type="Website User")
        fk.add("User", name="old@ec.vn", enabled=0, user_type="System User")
        fk.set_user(ME)
        self.fk = fk
        self.r = fk.load("ecentric_workspace.pm.api.rooms")

    def tearDown(self):
        sys.modules.pop("requests", None)

    def room(self, out, code):
        return [x for x in out["rooms"] if x["code"] == code][0]


class TestDay(Base):
    def test_one_batch_teams_bookings_busy_mine_by_organiser(self):
        self.g.room_cal["room.phong@ecentric.vn"] = [gev("a", "09:30", "10:30"),
                                                    gev("b", "14:00", "15:00", org=ME, name="Alice"),
                                                    gev("c", "16:00", "17:00", showAs="free")]
        out = self.r.day()
        self.assertEqual(len(self.g.batches()), 1)
        self.assertEqual([x["label"] for x in out["rooms"]], ["5.1 - Phong", "1.2 - Thổ", "5.2 - Cabin"])
        b = self.room(out, "5.1")["bookings"]
        self.assertEqual([(x["start"][11:16], x["who"], x["mine"]) for x in b],
                         [("09:30", "Bob", False), ("14:00", "Alice", True)])   # free slot ignored
        self.assertNotIn("org", b[0])                                         # no e-mail leaked

    def test_room_not_created_yet_and_sync_off_never_500(self):
        del self.g.room_cal["room.cabin@ecentric.vn"]
        self.assertEqual(self.room(self.r.day(), "5.2")["error"], "ROOM_NOT_FOUND")
        self.fk.module.get_conf = lambda: {}
        out = self.r.day()
        self.assertFalse(out["sync_on"])
        self.assertTrue(all(x["error"] == "SYNC_OFF" for x in out["rooms"]))

    def test_cache_60s_then_invalidated_by_booking(self):
        self.r.day(); self.r.day()
        self.assertEqual(len(self.g.batches()), 1)
        self.r.clear_cache()
        self.r.day()
        self.assertEqual(len(self.g.batches()), 2)

    def test_disabled_room_hidden(self):
        self.fk.row("EC Meeting Room", "1.2")["enabled"] = 0
        self.assertEqual([x["code"] for x in self.r.day()["rooms"]], ["5.1", "5.2"])


class TestBook(Base):
    def test_book_creates_teams_event_on_my_calendar_with_room_resource(self):
        out = self.r.book("1.2", DAY + " 10:00:00", DAY + " 11:00:00", "Review brand",
                          attendees=json.dumps(["carol@ec.vn", ME]))
        post = [c for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")][0]
        self.assertIn("/users/alice%40ec.vn/events", post[1])
        body = post[2]
        self.assertEqual(body["attendees"][0], {"emailAddress": {"address": "room.tho@ecentric.vn",
                                                                 "name": "1.2 - Thổ"}, "type": "resource"})
        self.assertEqual([a["emailAddress"]["address"] for a in body["attendees"][1:]], ["carol@ec.vn"])
        self.assertTrue(body["isOnlineMeeting"])
        self.assertEqual(body["location"]["locationEmailAddress"], "room.tho@ecentric.vn")
        self.assertEqual((out["state"], out["label"], out["join_url"]), ("pending", "1.2 - Thổ", "https://teams/x"))

    def test_clash_refused_after_fresh_read(self):
        self.r.day()   # cached empty
        self.g.room_cal["room.tho@ecentric.vn"] = [gev("t", "10:30", "11:30", name="Vu")]
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 10:00:00", DAY + " 11:00:00", "Hop")
        self.assertIn("10:30", str(cm.exception))
        self.assertFalse([c for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")])

    def test_back_to_back_is_not_a_clash(self):
        self.g.room_cal["room.tho@ecentric.vn"] = [gev("t", "09:00", "10:00")]
        self.assertTrue(self.r.book("1.2", DAY + " 10:00:00", DAY + " 10:30:00", "Hop")["ok"])

    def test_input_guards(self):
        for s, e in ((DAY + " 11:00:00", DAY + " 10:00:00"), (DAY + " 08:00:00", DAY + " 19:00:00"),
                     ("2026-10-15 10:00:00", "2026-10-15 11:00:00")):
            with self.assertRaises(Exception):
                self.r.book("1.2", s, e, "Hop")
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "  ")
        for bad in (["old@ec.vn"], ["khong-phai-email"], ["a@b"]):
            with self.assertRaises(Exception):
                self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", attendees=json.dumps(bad))
        with self.assertRaises(Exception):
            self.r.book("9.9", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")

    def test_room_not_on_m365_refused(self):
        del self.g.room_cal["room.tho@ecentric.vn"]
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        self.assertIn("Microsoft 365", str(cm.exception))

    def test_graph_refuses_create_is_logged_and_friendly(self):
        self.g.create_status = 403
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        self.assertIn("403", str(cm.exception))

    def test_booking_invalidates_day_cache(self):
        self.r.day()
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        n = len(self.g.batches())
        self.r.day()
        self.assertEqual(len(self.g.batches()), n + 1)


class TestStateMineCancel(Base):
    def booked(self):
        return self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Giao ban")["event_id"]

    def test_state_follows_room_answer(self):
        eid = self.booked()
        self.assertEqual(self.r.booking_state(eid)["state"], "pending")
        self.g.my_events[eid]["attendees"][0]["status"]["response"] = "accepted"
        self.assertEqual(self.r.booking_state(eid)["state"], "accepted")
        self.g.my_events[eid]["attendees"][0]["status"]["response"] = "declined"
        self.assertEqual(self.r.booking_state(eid)["state"], "declined")

    def test_mine_lists_room_bookings_only(self):
        eid = self.booked()
        self.g.my_events["X"] = {"id": "X", "subject": "Khong phong", "isOrganizer": True, "attendees": [],
                                 "start": {"dateTime": DAY + "T12:00:00"}, "end": {"dateTime": DAY + "T13:00:00"}}
        rows = self.r.mine()["rows"]
        self.assertEqual([(x["event_id"], x["label"], x["subject"], x["state"]) for x in rows],
                         [(eid, "5.1 - Phong", "Giao ban", "pending")])

    def test_cancel_only_organiser(self):
        eid = self.booked()
        self.g.my_events[eid]["isOrganizer"] = False
        with self.assertRaises(Exception):
            self.r.cancel(eid)
        self.g.my_events[eid]["isOrganizer"] = True
        self.assertEqual(self.r.cancel(eid)["state"], "cancelled")
        self.assertTrue(self.g.my_events[eid]["isCancelled"])
        self.assertEqual(self.r.booking_state(eid)["state"], "cancelled")


class TestV2(Base):
    """06/11/2026: đặt trên ERP đơn giản như Teams - khách ngoài, lặp lại, đổi giờ/phòng, huỷ chuỗi."""

    def created(self):
        return [c[2] for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")]

    def test_external_guest_invited_and_counted(self):
        out = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Gap brand",
                          attendees=json.dumps(["Partner@Brand.com", "carol@ec.vn", "web@ec.vn"]))
        mails = [a["emailAddress"]["address"] for a in self.created()[0]["attendees"][1:]]
        self.assertEqual(mails, ["partner@brand.com", "carol@ec.vn", "web@ec.vn"])
        self.assertEqual(out["external"], 2)
        g = self.r.mine()["rows"][0]["guests"]
        self.assertEqual([(x["email"], x["external"]) for x in g],
                         [("partner@brand.com", True), ("carol@ec.vn", False), ("web@ec.vn", True)])   # Website User = khách ngoài, như book()

    def test_weekly_series_body_and_every_occurrence_checked(self):
        # 2026-10-16 is a Friday; a clash on the 3rd Friday must refuse the whole series
        self.g.room_cal["room.tho@ecentric.vn"] = [
            gev("x", "10:00", "11:00", start={"dateTime": "2026-10-30T10:30:00"}, end={"dateTime": "2026-10-30T11:30:00"})]
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 10:00:00", DAY + " 11:00:00", "Giao ban", repeat="weekly",
                        repeat_until="2026-11-20")
        self.assertIn("30/10", str(cm.exception))
        self.assertFalse(self.created())
        self.g.room_cal["room.tho@ecentric.vn"] = []
        out = self.r.book("1.2", DAY + " 10:00:00", DAY + " 11:00:00", "Giao ban", repeat="weekly",
                          repeat_until="2026-11-20")
        rec = self.created()[0]["recurrence"]
        self.assertEqual(rec["pattern"], {"type": "weekly", "interval": 1, "daysOfWeek": ["friday"],
                                          "firstDayOfWeek": "monday"})
        self.assertEqual(rec["range"], {"type": "endDate", "startDate": DAY, "endDate": "2026-11-20"})
        self.assertTrue(out["recurring"])

    def test_occurrences_patterns(self):
        occ = self.r._occurrences
        wk = self.r._recurrence("weekdays", "2026-10-23", DAY + " 09:00:00")
        self.assertEqual([x[0][:10] for x in occ(DAY + " 09:00:00", DAY + " 10:00:00", wk)],
                         ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"])
        bi = self.r._recurrence("biweekly", "2026-11-30", DAY + " 09:00:00")
        self.assertEqual([x[0][:10] for x in occ(DAY + " 09:00:00", DAY + " 10:00:00", bi)],
                         ["2026-10-16", "2026-10-30", "2026-11-13", "2026-11-27"])
        mo = self.r._recurrence("monthly", "2027-01-31", DAY + " 09:00:00")
        self.assertEqual(len(occ(DAY + " 09:00:00", DAY + " 10:00:00", mo)), 4)

    def test_repeat_guards(self):
        for rep, until in (("weekly", None), ("weekly", "2026-10-01"), ("weekly", "2027-06-01"), ("hourly", "2026-11-01")):
            with self.assertRaises(Exception):
                self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", repeat=rep, repeat_until=until)

    def test_update_time_same_room_ignores_own_meeting(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")["event_id"]
        # the room now carries my meeting (same uid) + someone else at 17:00
        self.g.room_cal["room.tho@ecentric.vn"] = [gev("m", "15:00", "16:00", org=ME, name="Alice", iCalUId="uid-" + eid),
                                                  gev("o", "17:00", "18:00")]
        out = self.r.update(eid, start=DAY + " 15:30:00", end=DAY + " 16:30:00")
        p = [c for c in self.g.calls if c[0] == "PATCH"][-1][2]
        self.assertEqual((p["start"]["dateTime"], p["end"]["dateTime"]), (DAY + "T15:30:00", DAY + "T16:30:00"))
        self.assertNotIn("attendees", p)
        self.assertEqual(out["state"], "pending")
        with self.assertRaises(Exception) as cm:
            self.r.update(eid, start=DAY + " 16:30:00", end=DAY + " 17:30:00")
        self.assertIn("17:00", str(cm.exception))

    def test_update_room_swaps_resource_keeps_guests(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop",
                          attendees=json.dumps(["carol@ec.vn", "x@partner.vn"]))["event_id"]
        self.g.room_cal["room.phong@ecentric.vn"] = [gev("p", "15:30", "16:30")]
        with self.assertRaises(Exception):
            self.r.update(eid, room="5.1")
        self.g.room_cal["room.phong@ecentric.vn"] = []
        self.r.update(eid, room="5.1")
        p = [c for c in self.g.calls if c[0] == "PATCH"][-1][2]
        self.assertEqual([a["emailAddress"]["address"] for a in p["attendees"]],
                         ["room.phong@ecentric.vn", "carol@ec.vn", "x@partner.vn"])
        self.assertEqual(p["attendees"][0]["type"], "resource")
        self.assertEqual(p["location"]["locationEmailAddress"], "room.phong@ecentric.vn")
        self.assertEqual(self.r.mine()["rows"][0]["label"], "5.1 - Phong")

    def test_update_only_organiser_and_title_only_patch(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")["event_id"]
        self.r.update(eid, subject="Hop moi")
        p = [c for c in self.g.calls if c[0] == "PATCH"][-1][2]
        self.assertEqual(p, {"subject": "Hop moi"})
        self.g.my_events[eid]["isOrganizer"] = False
        with self.assertRaises(Exception):
            self.r.update(eid, subject="x")

    def test_cancel_series_targets_master(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", repeat="daily",
                          repeat_until="2026-10-20")["event_id"]
        self.g.my_events["OCC1"] = dict(self.g.my_events[eid], id="OCC1", type="occurrence", seriesMasterId=eid)
        self.r.cancel("OCC1", scope="series")
        self.assertTrue([c for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events/" + eid + "/cancel")])
        with self.assertRaises(Exception):
            self.r.cancel(self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Don")["event_id"], scope="series")


class TestIntegratorFollowUps(Base):
    """06/11: transactionId chống tạo trùng; lặp T2-T6 không bắt đầu cuối tuần; lỗi Graph không cache."""

    def test_transaction_id_forwarded_only_when_safe(self):
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", txn="erp-abc12345")
        self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", txn="bad id; drop")
        bodies = [c[2] for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")]
        self.assertEqual(bodies[0].get("transactionId"), "erp-abc12345")
        self.assertNotIn("transactionId", bodies[1])

    def test_weekdays_series_cannot_start_on_weekend(self):
        with self.assertRaises(Exception):   # 2026-10-17 = Saturday
            self.r.book("1.2", "2026-10-17 09:00:00", "2026-10-17 10:00:00", "Hop", repeat="weekdays",
                        repeat_until="2026-10-30")

    def test_graph_error_not_cached(self):
        self.g.batch_status = 429
        self.assertTrue(self.r.day()["rooms"][0].get("error"))
        self.g.batch_status = 200
        self.assertFalse(self.r.day()["rooms"][0].get("error"))


class TestDescription(Base):
    """06/11: mô tả cuộc họp - đặt có mô tả, sửa mô tả giữ khối Teams, mô tả viết trên Teams chỉ đọc."""
    TEAMS = ("<html><body>%s<div>________________________________________________________________________________</div>"
             "<div>Microsoft Teams meeting</div><a href='https://teams.microsoft.com/l/x'>Join</a></body></html>")

    def test_book_with_description_escaped_and_marked(self):
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", description="Dòng 1\n<b>x</b> & y")
        body = [c[2] for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")][0]["body"]
        self.assertEqual(body["contentType"], "HTML")
        self.assertEqual(body["content"], '<div data-erp-desc="1">Dòng 1<br>&lt;b&gt;x&lt;/b&gt; &amp; y</div><!--/erp-desc-->')

    def test_no_description_no_body(self):
        self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", description="   ")
        body = [c[2] for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")][0]
        self.assertNotIn("body", body)

    def test_detail_and_update_keep_teams_block(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", description="Agenda cu")["event_id"]
        ev = self.g.my_events[eid]
        ev["body"] = {"content": self.TEAMS % ev["body"]["content"]}      # Exchange appends the join block
        self.assertEqual(self.r.detail(eid), {"description": "Agenda cu", "editable": True})
        self.r.update(eid, description="Agenda moi\n- muc 1")
        new = [c for c in self.g.calls if c[0] == "PATCH"][-1][2]["body"]["content"]
        self.assertIn("Agenda moi<br>- muc 1", new)
        self.assertNotIn("Agenda cu", new)
        self.assertIn("https://teams.microsoft.com/l/x", new)
        self.assertEqual(self.r.detail(eid)["description"], "Agenda moi\n- muc 1")

    def test_same_description_not_patched(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", description="A")["event_id"]
        out = self.r.update(eid, description="A")
        self.assertTrue(out.get("unchanged"))

    def test_teams_written_description_read_only(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")["event_id"]
        self.g.my_events[eid]["body"] = {"content": self.TEAMS % "<p>Viết trên Teams</p>"}
        self.assertEqual(self.r.detail(eid), {"description": "Viết trên Teams", "editable": False})
        with self.assertRaises(Exception):
            self.r.update(eid, description="khác")

    def test_add_description_to_meeting_without_one(self):
        eid = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")["event_id"]
        self.g.my_events[eid]["body"] = {"content": self.TEAMS % ""}
        self.assertEqual(self.r.detail(eid), {"description": "", "editable": True})
        self.r.update(eid, description="Mới")
        new = [c for c in self.g.calls if c[0] == "PATCH"][-1][2]["body"]["content"]
        self.assertTrue(new.startswith('<html><body><div data-erp-desc="1">Mới</div><!--/erp-desc-->'))

    def test_description_too_long(self):
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", description="x" * 4001)


class TestSeedPatch(unittest.TestCase):
    def test_p032_seeds_five_rooms_once_and_keeps_edits(self):
        fk = _pm_fake.install()
        fk.doctypes.add("EC Meeting Room")
        fk.autoname["EC Meeting Room"] = lambda d: d["room_code"]   # autoname field:room_code
        p = fk.load("ecentric_workspace.pm.patches.p032_pm_meeting_rooms_seed")
        p.execute()
        self.assertEqual(sorted(fk.db.t("EC Meeting Room")), ["1.1", "1.2", "1.3", "5.1", "5.2"])
        fk.row("EC Meeting Room", "5.2")["capacity"] = 2
        p.execute()
        self.assertEqual(fk.row("EC Meeting Room", "5.2")["capacity"], 2)
        self.assertEqual(fk.row("EC Meeting Room", "1.1")["room_title"], "Hoả")


class TestCapacityPatch(unittest.TestCase):
    def test_p033_fills_empty_capacity_only(self):
        fk = _pm_fake.install()
        fk.doctypes.add("EC Meeting Room")
        for code, cap in (("5.1", None), ("1.1", 10), ("5.2", 0)):
            fk.add("EC Meeting Room", name=code, room_code=code, room_title="x", email=code + "@x.vn", capacity=cap, enabled=1)
        fk.load("ecentric_workspace.pm.patches.p033_pm_meeting_rooms_capacity").execute()
        self.assertEqual([fk.row("EC Meeting Room", c)["capacity"] for c in ("5.1", "1.1", "5.2")], [8, 10, 2])


class TestDatTam(Base):
    """13/11/2026: Microsoft 365 loi (Graph timeout) -> dat tam tren ERP, tu len Teams khi chay lai."""

    def setUp(self):
        Base.setUp(self)
        store = {}
        self.fk.module.db.get_global = lambda k, *a, **kw: store.get(k)
        self.fk.module.db.set_global = lambda k, v, *a, **kw: store.__setitem__(k, v)
        cache = self.fk.module.cache()
        cache.delete_value = lambda k: cache.d.pop(k, None)
        self.cache = cache
        self.down = True
        real_post = self.g.post

        def post(url, json=None, headers=None, timeout=None, **k):
            if self.down:
                raise IOError("Read timed out")       # Graph treo nhu sang 13/11
            return real_post(url, json=json, headers=headers, timeout=timeout, **k)
        sys.modules["requests"].post = post
        self.H = sys.modules["ecentric_workspace.pm.api.rooms_hold"]

    def up(self):
        self.down = False
        self.cache.d.pop(self.H.DOWN_KEY, None)

    def test_microsoft_loi_day_khong_bao_loi_va_bat_dat_tam(self):
        d = self.r.day(DAY)
        self.assertTrue(d["offline"])
        self.assertFalse(any(r.get("error") for r in d["rooms"]))
        n = len(self.g.calls)
        self.assertTrue(self.r.day(DAY)["offline"])          # lan sau: khong goi Graph (khong cho 15 s)
        self.assertEqual(len(self.g.calls), n)

    def test_dat_tam_chan_trung_hien_tren_luoi_va_mine(self):
        self.r.day(DAY)
        res = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop gap", txn="abcdefgh-1234")
        self.assertEqual(res["state"], "held")
        self.assertTrue(res["event_id"].startswith("hold:"))
        self.assertFalse([c for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")])
        self.fk.set_user("carol@ec.vn")
        with self.assertRaises(Exception) as cm:
            self.r.book("1.2", DAY + " 15:30:00", DAY + " 16:30:00", "Trung")
        self.assertIn("đặt tạm", str(cm.exception))
        self.r.book("1.2", DAY + " 16:00:00", DAY + " 17:00:00", "Sat gio")      # sat gio: duoc
        self.fk.set_user(ME)
        room = [r for r in self.r.day(DAY)["rooms"] if r["name"] == "1.2"][0]
        self.assertEqual(len(room["bookings"]), 2)
        self.assertTrue(any(b["mine"] and "đặt tạm" in b["who"] for b in room["bookings"]))
        rows = self.r.mine()["rows"]
        self.assertEqual([x["state"] for x in rows], ["held"])
        with self.assertRaises(Exception):
            self.r.update(res["event_id"], subject="Doi")
        with self.assertRaises(Exception):
            self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Lap", repeat="daily",
                        repeat_until="2026-10-20")

    def test_huy_dat_tam(self):
        self.r.day(DAY)
        res = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop")
        self.assertEqual(self.r.cancel(res["event_id"])["state"], "cancelled")
        room = [r for r in self.r.day(DAY)["rooms"] if r["name"] == "1.2"][0]
        self.assertEqual(room["bookings"], [])

    def test_microsoft_chay_lai_tu_len_teams(self):
        self.r.day(DAY)
        res = self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", attendees=["carol@ec.vn"],
                          txn="abcdefgh-1234")
        self.fk.set_user("carol@ec.vn")
        res2 = self.r.book("5.1", DAY + " 15:00:00", DAY + " 16:00:00", "Bi trung")
        self.fk.set_user(ME)
        self.g.room_cal["room.phong@ecentric.vn"] = [gev("T1", "15:30", "16:30")]   # dat tren Teams luc dang loi
        self.H.sync_holds()                       # van loi: khong lam gi
        self.assertEqual(self.H.get(res["event_id"])["status"], "held")
        self.up()
        self.H.sync_holds()
        h = self.H.get(res["event_id"])
        self.assertEqual(h["status"], "synced")
        post = [c for c in self.g.calls if c[0] == "POST" and c[1].endswith("/events")]
        self.assertEqual(len(post), 1)
        self.assertIn("alice%40ec.vn/events", post[0][1].replace("@", "%40"))
        self.assertEqual(post[0][2]["transactionId"], "abcdefgh-1234")
        self.assertTrue(post[0][2]["isOnlineMeeting"])
        self.assertEqual(self.H.get(res2["event_id"])["status"], "declined")
        room = [r for r in self.r.day(DAY)["rooms"] if r["name"] == "1.2"][0]
        self.assertFalse(any("đặt tạm" in b["who"] for b in room["bookings"]))


if __name__ == "__main__":
    unittest.main()
