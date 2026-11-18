# Copyright (c) 2026, eCentric and contributors
"""18/11: EC AI Live Session.lc_open_before_min - "Mo tab truoc gio live (phut)", 1..60, trong = theo cai dat tren app.
Di qua Nhap -> Phat hanh nhu may / kenh OBS / khung gio; get_config tra o tung phien (canh schedule), chi khi co gia tri.
    python -m pytest -q ecentric_workspace/ai_tools/tests/test_ai_live_open_before.py"""
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.tests.test_ai_live_schedule_publish import DAILY, World, at
from ecentric_workspace.ai_tools.tests.test_ai_live_session import FakeMachines, FakeSessions, doc, sess, slot, ts

KEY = "lc_open_before_min"


class TestOpenBeforeDraftPublish(unittest.TestCase):
    def test_draft_then_publish_reaches_app(self):
        w = World(at(12))
        self.assertNotIn(KEY, w.lives()["a"])                          # trong = khong gui -> app theo cai dat cua no
        r = w.draft("a", lc_open_before_min="10")
        self.assertEqual(r["diff"], ["Mở tab trước giờ live theo app → 10 phút"])
        self.assertEqual(w.ss.get("a")["draft"], {KEY: 10})
        self.assertNotIn(KEY, w.lives()["a"])                          # nhap chua toi app
        w.publish()
        lv = w.lives()["a"]
        self.assertEqual(lv[KEY], 10)
        self.assertIn("schedule", lv)
        self.assertIsNone(w.ss.get("a").get("draft"))

    def test_clear_goes_back_to_app_setting(self):
        w = World(at(12), [sess("a", lc_open_before_min=15)])
        self.assertEqual(w.lives()["a"][KEY], 15)
        r = w.draft("a", lc_open_before_min="")
        self.assertEqual(r["diff"], ["Mở tab trước giờ live 15 phút → theo app"])
        w.publish()
        self.assertNotIn(KEY, w.lives()["a"])
        self.assertIsNone(w.ss.get("a")[KEY])

    def test_same_as_published_clears_draft_and_other_fields_untouched(self):
        w = World(at(12), [sess("a", lc_open_before_min=15)])
        w.draft("a", lc_open_before_min="20")
        w.draft("a", lc_open_before_min="15")
        self.assertIsNone(w.ss.get("a").get("draft"))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])            # sua khung khong dung toi truong nay
        self.assertNotIn(KEY, w.ss.get("a")["draft"])
        w.publish()
        self.assertEqual(w.lives()["a"][KEY], 15)

    def test_bad_values(self):
        w = World(at(12))
        for bad in ("0", "61", "-5", "abc", "1.5", 100):
            with self.assertRaises(C.AiLiveError) as e:
                w.draft("a", lc_open_before_min=bad)
            self.assertEqual(str(e.exception), C.SessMsg.BAD_OPEN_BEFORE)
        for ok in ("1", 60, " 30 ", "5.0"):
            w.draft("a", lc_open_before_min=ok)
        self.assertEqual(w.ss.get("a")["draft"], {KEY: 5})

    def test_app_slot_edit_keeps_value(self):
        w = World(at(12), [sess("a", lc_open_before_min=7)])
        w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}], base=0)
        self.assertEqual(w.lives()["a"][KEY], 7)

    def test_held_old_version_from_before_this_field(self):
        s = sess("a", lc_open_before_min=12, held_until_ts=at(23),
                 prev={"slots": [slot("18:00", "22:00", DAILY)], "machine": "MAY01", "obs_port": 0, "version": 1})
        v = P.served_view(s, at(19))
        self.assertEqual((v["held_until"], v[KEY]), (at(23), 12))       # ban cu chua co truong -> lay ban phat hanh
        self.assertEqual(P.served_view(dict(s, prev=dict(s["prev"], **{KEY: None})), at(19))[KEY], None)

    def test_rules(self):
        self.assertEqual([P.open_before(v) for v in (None, "", 0, "0", "x", 9, "9")], [None, None, None, None, None, 9, 9])
        a = P.published_view(sess("a"))
        self.assertTrue(P.same(a, dict(a, **{KEY: None})))
        self.assertFalse(P.same(a, dict(a, **{KEY: 3})))
        self.assertEqual(P.draft_of(dict(a, **{KEY: 3}), a), {KEY: 3})


class TestOpenBeforeDesk(unittest.TestCase):
    def setUp(self):
        self.svc = ValidateSessionService(FakeSessions([]), FakeMachines(), clock=lambda: ts(2026, 10, 19, 12))

    def test_range(self):
        for ok in (None, "", 0, 1, 60):
            self.svc.execute(doc(lc_open_before_min=ok))
        for bad in (61, 120):
            with self.assertRaises(C.AiLiveError) as e:
                self.svc.execute(doc(lc_open_before_min=bad))
            self.assertEqual(str(e.exception), C.SessMsg.BAD_OPEN_BEFORE)


if __name__ == "__main__":
    unittest.main()
