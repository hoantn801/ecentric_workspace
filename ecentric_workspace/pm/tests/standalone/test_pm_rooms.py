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

    def get(self, url, headers=None, timeout=None, **k):
        self.calls.append(("GET", url))
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
        req.get, req.post = self.g.get, self.g.post
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
        with self.assertRaises(Exception):
            self.r.book("1.2", DAY + " 15:00:00", DAY + " 16:00:00", "Hop", attendees=json.dumps(["web@ec.vn"]))
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


if __name__ == "__main__":
    unittest.main()
