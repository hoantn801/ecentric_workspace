# -*- coding: utf-8 -*-
"""RSVP lich hop (PO 05/11/2026: "thinh thoang phan hoi RSVP roi ma bam lai no khong luu").

Graph is mocked: `requests` is replaced by a tiny router so every call made by
pm.api.schedule is recorded and answered from a fake mailbox. The fake reproduces the
Graph behaviour behind the report: accept/decline/tentativelyAccept answer 202 and the
event's responseStatus is only updated LATER (here: never, i.e. a stale read).

Run: python3 -m unittest discover -s ecentric_workspace/pm/tests/standalone \
       -t ecentric_workspace/pm/tests/standalone -p "test_*.py"
"""
import json
import sys
import types
import unittest

import _pm_fake

ME = "me@ec.vn"
OTHER = "other@ec.vn"
DAY = "2026-10-16"   # _pm_fake TODAY


class _Resp(object):
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


class FakeGraph(object):
    """Fake mailbox. `events` = list of Graph event dicts; `apply_answers` False = the
    202-then-later behaviour (reads straight after an answer still see the old status)."""

    def __init__(self, events, apply_answers=False, post_status=202, post_error=None,
                 require_no_send_when_not_requested=True):
        self.events = events
        self.apply_answers = apply_answers
        self.post_status = post_status
        self.post_error = post_error
        self.strict = require_no_send_when_not_requested
        self.calls = []

    def _ev(self, url):
        for ev in self.events:
            from urllib.parse import quote
            if "/events/" + quote(ev["id"], safe="") in url:
                return ev
        return None

    def get(self, url, headers=None, timeout=None, **k):
        self.calls.append(("GET", url, None))
        if "/calendarView" in url:
            return _Resp(200, {"value": [dict(e) for e in self.events]})
        ev = self._ev(url)
        if ev is None:
            return _Resp(404, {"error": {"code": "ErrorItemNotFound"}})
        return _Resp(200, {"responseRequested": ev.get("responseRequested", True),
                           "isOrganizer": ev.get("isOrganizer", False),
                           "isCancelled": ev.get("isCancelled", False)})

    def post(self, url, headers=None, json=None, timeout=None, **k):
        self.calls.append(("POST", url, json))
        if self.post_status not in (200, 202, 204):
            return _Resp(self.post_status, {"error": {"code": self.post_error or "X"}})
        ev = self._ev(url)
        if ev is None:
            return _Resp(404, {"error": {"code": "ErrorItemNotFound"}})
        if self.strict and ev.get("responseRequested") is False and (json or {}).get("sendResponse"):
            # Exchange refuses to send a reply the organiser did not ask for.
            return _Resp(400, {"error": {"code": "ErrorInvalidRequest"}})
        if self.apply_answers:
            st = {"accept": "accepted", "decline": "declined",
                  "tentativelyAccept": "tentativelyAccepted"}[url.rsplit("/", 1)[1]]
            ev["responseStatus"] = {"response": st}
        return _Resp(202)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def ev(i, hh, resp="notResponded", **kw):
    e = {"id": i, "subject": "Hop " + i, "isAllDay": False, "showAs": "tentative",
         "isOrganizer": resp == "organizer", "type": "singleInstance",
         "start": {"dateTime": DAY + "T%02d:00:00.0000000" % hh},
         "end": {"dateTime": DAY + "T%02d:30:00.0000000" % hh},
         "responseStatus": {"response": resp}}
    e.update(kw)
    return e


class Base(unittest.TestCase):
    def boot(self, graph):
        fk = _pm_fake.install()
        fk.module.get_conf = lambda: {"ec_pm_calendar_sync": 1}
        fk.utils.time_diff_in_hours = lambda a, b: (
            fk.utils.get_datetime(a) - fk.utils.get_datetime(b)).total_seconds() / 3600.0
        perm = types.ModuleType("ecentric_workspace.pm.permissions")
        perm.require_pm_access = lambda *a, **k: None
        perm.can_see_all_pm_data = lambda *a, **k: False
        g = types.ModuleType("ecentric_workspace.notification_center.providers.graph")
        g.is_configured = lambda *a: True
        g.get_app_token = lambda *a: (True, "tok")
        req = types.ModuleType("requests")
        req.get, req.post = graph.get, graph.post
        req.patch = lambda *a, **k: _Resp(200)
        sys.modules.update({
            "ecentric_workspace.pm.permissions": perm,
            "ecentric_workspace.notification_center": types.ModuleType("x"),
            "ecentric_workspace.notification_center.providers": types.ModuleType("y"),
            "ecentric_workspace.notification_center.providers.graph": g,
            "requests": req})
        sys.modules["ecentric_workspace.notification_center.providers"].graph = g
        fk.set_user(ME)
        self.fk = fk
        self.g = graph
        self.s = fk.load("ecentric_workspace.pm.api.schedule")
        return self.s

    def tearDown(self):
        sys.modules.pop("requests", None)

    def week_resp(self, eid, user=ME):
        rows = self.s._ms_meetings(user, DAY + " 00:00:00", "2026-10-23 00:00:00")
        return {r.get("id"): r.get("response") for r in rows}.get(eid)

    def today_resp(self, eid):
        return {r["id"]: r["response"] for r in self.s._ms_today_events(ME)}.get(eid)

    def open_rsvp_todos(self):
        return [t for t in self.fk.db.t("ToDo").values()
                if t.get("status") == "Open" and "[RSVPHOP]" in (t.get("description") or "")]


class StaleReadAfterAnswer(Base):
    """Bug 1 (main): Graph 202 -> immediate re-read still says notResponded."""

    def test_week_view_shows_answer_right_after_rsvp(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        self.assertTrue(s.rsvp("E1", "accept")["ok"])
        self.assertEqual(self.week_resp("E1"), "accepted")

    def test_home_widget_shows_answer_right_after_rsvp(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s.rsvp("E1", "tentative")
        self.assertEqual(self.today_resp("E1"), "tentativelyAccepted")

    def test_rsvp_returns_graph_status_for_the_ui(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        res = s.rsvp("E1", "decline")
        self.assertEqual((res["ok"], res["response"], res["status"]), (True, "decline", "declined"))

    def test_changing_answer_overrides_previous_one(self):
        s = self.boot(FakeGraph([ev("E1", 9, "accepted")]))
        s.rsvp("E1", "tentative")
        self.assertEqual(self.week_resp("E1"), "tentativelyAccepted")

    def test_overlay_expires_and_graph_wins_again(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s.rsvp("E1", "accept")
        self.fk.advance(seconds=s._RSVP_OVERLAY_TTL + 5)
        self.assertEqual(self.week_resp("E1"), "notResponded")

    def test_overlay_is_per_user_and_never_on_masked_view(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s.rsvp("E1", "accept")
        self.assertEqual(self.week_resp("E1", user=OTHER), "notResponded")
        masked = s._ms_meetings(ME, DAY + " 00:00:00", "2026-10-23 00:00:00", mask=True)
        self.assertNotIn("response", masked[0])

    def test_organizer_never_overridden(self):
        s = self.boot(FakeGraph([ev("E1", 9, "organizer")]))
        s._remember_rsvp(ME, "E1", "accepted")
        self.assertEqual(self.week_resp("E1"), "organizer")

    def test_failed_rsvp_is_not_remembered(self):
        s = self.boot(FakeGraph([ev("E1", 9)], post_status=403, post_error="ErrorAccessDenied"))
        res = s.rsvp("E1", "accept")
        self.assertFalse(res["ok"])
        self.assertEqual(self.week_resp("E1"), "notResponded")


class ReminderTodo(Base):
    """Bug 2: the [RSVPHOP] reminder refreshed inside rsvp() re-read Graph straight away,
    still counted the invite just answered and stayed open."""

    def test_last_invite_answered_closes_reminder(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s._ensure_rsvp_todo(ME, 1, ["16/10 09:00"])
        self.assertEqual(len(self.open_rsvp_todos()), 1)
        self.assertTrue(s.rsvp("E1", "accept")["ok"])
        self.assertEqual(self.open_rsvp_todos(), [])

    def test_reminder_decrements(self):
        s = self.boot(FakeGraph([ev("E1", 9), ev("E2", 14)]))
        s._ensure_rsvp_todo(ME, 2, ["16/10 09:00", "16/10 14:00"])
        s.rsvp("E1", "accept")
        todos = self.open_rsvp_todos()
        self.assertEqual(len(todos), 1)
        self.assertIn("(1 lời mời): 16/10 14:00", todos[0]["description"])

    def test_scheduler_does_not_reopen_within_overlay(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s.rsvp("E1", "accept")
        self.assertEqual(s._unanswered_invites(ME), 0)

    def test_cancelled_invite_not_counted(self):
        s = self.boot(FakeGraph([ev("E1", 9, isCancelled=True), ev("E2", 10)]))
        self.assertEqual(s._unanswered_invites(ME), 1)

    def test_unanswered_select_has_id(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s._unanswered_invites(ME)
        url = [c[1] for c in self.g.calls if "/calendarView" in c[1]][0]
        self.assertIn("$select=id,", url)


class ResponseNotRequested(Base):
    """Bug 3: organiser turned off 'Request responses' -> sendResponse=true is refused
    (400) and the answer is never stored -- only for those meetings ('thinh thoang')."""

    def test_no_reply_sent_when_not_requested(self):
        s = self.boot(FakeGraph([ev("E1", 9, responseRequested=False)]))
        res = s.rsvp("E1", "accept")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.g.posts()[-1][2], {"sendResponse": False})

    def test_reply_sent_when_requested(self):
        s = self.boot(FakeGraph([ev("E1", 9)]))
        s.rsvp("E1", "accept", comment="ok")
        self.assertEqual(self.g.posts()[-1][2], {"sendResponse": True, "comment": "ok"})

    def test_organizer_and_cancelled_get_clear_code(self):
        s = self.boot(FakeGraph([ev("E1", 9, "organizer"), ev("E2", 10, isCancelled=True)]))
        self.assertEqual(s.rsvp("E1", "accept")["code"], "RSVP_ORGANIZER")
        self.assertEqual(s.rsvp("E2", "accept")["code"], "RSVP_CANCELLED")
        self.assertEqual(self.g.posts(), [])


class Failures(Base):
    def test_graph_error_is_logged_with_code(self):
        s = self.boot(FakeGraph([ev("E1", 9)], post_status=403, post_error="ErrorAccessDenied"))
        res = s.rsvp("E1", "accept")
        self.assertEqual((res["ok"], res["code"], res.get("graph_code")),
                         (False, "RSVP_403", "ErrorAccessDenied"))
        self.assertTrue(any("RSVP_403" in str(e) for e in self.fk.errors), self.fk.errors)

    def test_event_id_is_url_encoded(self):
        s = self.boot(FakeGraph([ev("AAMk/x+y=", 9)]))
        self.assertTrue(s.rsvp("AAMk/x+y=", "accept")["ok"])
        self.assertIn("/events/AAMk%2Fx%2By%3D/accept", self.g.posts()[-1][1])


if __name__ == "__main__":
    unittest.main()
