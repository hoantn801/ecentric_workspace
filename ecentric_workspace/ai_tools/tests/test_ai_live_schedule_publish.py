# Copyright (c) 2026, eCentric and contributors
"""fix10g - Lich live ban nhap -> phat hanh: giu gio cu khi dang live / sap len song / may nhan muon, keo dai gio ket
thuc ap ngay, doi may khi dang live, suc chua tinh ca lan dang giu, app sua lich nhan luon (nhap thanh lech),
man Dong bo / Tuan / Thang. Chay ngoai Frappe."""
import unittest
from datetime import date

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.discard_draft_service import DiscardDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.get_config_service import GetConfigService
from ecentric_workspace.ai_tools.features.ai_live.application.month_schedule_service import MonthScheduleService
from ecentric_workspace.ai_tools.features.ai_live.application.publish_schedule_service import PublishScheduleService
from ecentric_workspace.ai_tools.features.ai_live.application.push_slots_service import PushSlotsService
from ecentric_workspace.ai_tools.features.ai_live.application.resolve_draft_service import ResolveDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.sync_overview_service import SyncOverviewService
from ecentric_workspace.ai_tools.features.ai_live.application.week_schedule_service import WeekScheduleService
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.tests.test_ai_live_service import FakeBrands, FakeSchedule
from ecentric_workspace.ai_tools.tests.test_ai_live_session import FakeCommands, FakeMachines, FakeSessions, sess, slot, ts

VIEW, NOBODY = ["EC AI Content"], ["Employee"]
DAILY = list(range(1, 8))


def at(h, mi=0, d=19):
    return ts(2026, 10, d, h, mi)                    # 19/10/2026 = thu Hai


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class World:
    def __init__(self, t, sessions=None):
        self.clock = Clock(t)
        self.ss = FakeSessions(sessions or [sess("a"), sess("b", slots=[slot("08:00", "10:00", DAILY)])])
        self.machines, self.sched, self.cmds = FakeMachines(), FakeSchedule(), FakeCommands()

    def draft(self, name, **kw):
        return SaveDraftService(self.ss, self.machines, self.clock).execute("op@ec", VIEW, name, **kw)

    def pub(self):
        return PublishScheduleService(self.ss, self.machines, self.sched, self.cmds, self.clock)

    def publish(self, names=None, urgent=None):
        return self.pub().execute("op@ec", VIEW, names, urgent)

    def config(self, machine="MAY01", user="u1"):
        return GetConfigService(self.machines, FakeBrands(), sessions=self.ss, schedule=self.sched, clock=self.clock).execute(
            user, machine)

    def lives(self, machine="MAY01", user="u1"):
        return {lv["id"]: lv for lv in self.config(machine, user)["lives"]}

    def app_push(self, live, slots, base=None, machine="MAY01", user="u1"):
        return PushSlotsService(self.machines, self.ss, publisher=self.pub(), clock=self.clock).execute(user, machine, live, slots,
                                                                                                        base)

    def overview(self):
        return SyncOverviewService(self.ss, self.machines, self.sched, publisher=self.pub(), clock=self.clock).execute(VIEW)


def starts(lv):
    return [(x["start"], x["end"]) for x in lv["schedule"]]


class TestDraftPublish(unittest.TestCase):
    def test_draft_does_not_reach_app_until_publish(self):
        w = World(at(12))
        r = w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        self.assertEqual(r["state"], C.DraftState.READY)
        self.assertEqual(r["diff"], ["mỗi ngày: 19:00–22:00 → 19:30–22:00"])
        self.assertEqual(starts(w.lives()["a"]), [("19:00", "22:00")])
        out = w.publish()
        self.assertTrue(out["published"])
        self.assertEqual((out["version"], out["refresh_sent"]), (1, ["MAY01"]))
        self.assertEqual(starts(w.lives()["a"]), [("19:30", "22:00")])
        self.assertEqual(w.config()["schedule_version"], 1)
        self.assertEqual(w.machines.rows["MAY01"]["cfg_version"], 1)       # may da nhan ban 1
        cmd = list(w.cmds.rows.values())[0]
        self.assertEqual((cmd["action"], cmd["machine"], cmd["args"]), (C.CMD_REFRESH, "MAY01", {"version": 1}))
        self.assertEqual(w.sched.log[0]["source"], C.PubSource.ERP)
        with self.assertRaises(C.AiLiveError):
            w.publish()                                                    # khong con nhap

    def test_draft_back_to_published_clears_and_permissions(self):
        w = World(at(12))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        self.assertEqual(w.draft("a", slots=[slot("19:00", "22:00", DAILY)])["state"], C.DraftState.NONE)
        with self.assertRaises(C.AiLivePermission):
            SaveDraftService(w.ss, w.machines, w.clock).execute("x", NOBODY, "a", slots=[])
        with self.assertRaises(C.AiLiveError):
            w.draft("a", machine="MAY02", slots=[slot("19:00", "22:00", DAILY), slot("21:00", "23:00", DAILY)])  # trung trong phien
        w.ss.rows["w"] = sess("w", brand="wilmar")
        with self.assertRaises(C.AiLiveError) as cm:
            w.draft("w", machine="MAY02")                                  # MAY02 chua giao wilmar
        self.assertIn("wilmar", str(cm.exception))

    def test_discard(self):
        w = World(at(12))
        w.draft("a", slots=[])
        w.draft("b", obs_port=4460)
        self.assertEqual(DiscardDraftService(w.ss, w.clock).execute("op", VIEW, '["a"]')["discarded"], ["a"])
        self.assertEqual(DiscardDraftService(w.ss, w.clock).execute("op", VIEW)["discarded"], ["b"])


class TestHolds(unittest.TestCase):
    def test_on_air_change_held_until_end(self):
        w = World(at(20))                                                  # a dang live 19-22
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        out = w.publish()
        self.assertEqual((out["changes"][0]["held_until"], out["changes"][0]["held_why"]), (at(22), C.HoldWhy.ON_AIR))
        lv = w.lives()["a"]
        self.assertEqual((starts(lv), lv["held_until"]), ([("19:00", "22:00")], at(22)))
        w.clock.t = at(22, 1)
        self.assertEqual((starts(w.lives()["a"]), w.lives()["a"]["held_until"]), ([("19:30", "22:00")], None))

    def test_extend_end_applies_now_shorten_is_held(self):
        w = World(at(20))
        w.draft("a", slots=[slot("19:00", "23:00", DAILY)])
        self.assertEqual(w.publish()["changes"][0]["held_until"], 0)
        self.assertEqual(starts(w.lives()["a"]), [("19:00", "23:00")])
        w.draft("a", slots=[slot("19:00", "21:00", DAILY)])
        self.assertEqual(w.publish()["changes"][0]["held_until"], at(23))

    def test_soon_lock_and_urgent(self):
        w = World(at(18, 50))                                              # 19:00 len song trong 10 phut
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        self.assertEqual(w.publish()["changes"][0]["held_why"], C.HoldWhy.SOON)
        w2 = World(at(18, 50))
        w2.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        out = w2.publish(urgent=["a"])
        self.assertEqual((out["changes"][0]["held_until"], w2.sched.log[0]["source"]), (0, C.PubSource.URGENT))
        w3 = World(at(18, 30))                                             # con 30 phut > 15 -> ap ngay
        w3.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        self.assertEqual(w3.publish()["changes"][0]["held_until"], 0)
        w4 = World(at(18, 50))                                             # doi khung KHAC, lan 19:00 giu nguyen
        w4.draft("a", slots=[slot("19:00", "22:00", DAILY), slot("09:00", "10:00", [6])])
        self.assertEqual(w4.publish()["changes"][0]["held_until"], 0)

    def test_late_fetch_keeps_old_time(self):
        w = World(at(18, 59))                                              # 22:59 doi gio cho live 23:00 (o day 19:00)
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish(urgent=["a"])
        w.clock.t = at(19, 1)                                              # may tai lich SAU khi da len live gio cu
        lv = w.lives()["a"]
        self.assertEqual((starts(lv), lv["held_until"]), ([("19:00", "22:00")], at(22)))
        self.assertEqual(w.ss.get("a")["held_why"], C.HoldWhy.LATE)
        w.clock.t = at(19, 10)
        self.assertEqual(starts(w.lives()["a"]), [("19:00", "22:00")])     # van giu toi het lan do

    def test_fetch_before_start_gets_new_time(self):
        w = World(at(18, 59))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish(urgent=["a"])
        w.clock.t = at(18, 59, ) + 20
        self.assertEqual(starts(w.lives()["a"]), [("19:30", "22:00")])     # nhan kip truoc 19:00
        w.clock.t = at(19, 1)
        self.assertEqual(starts(w.lives()["a"]), [("19:30", "22:00")])
        self.assertEqual(w.ss.get("a")["held_until_ts"], 0)

    def test_move_machine_while_on_air(self):
        w = World(at(20))
        w.draft("a", machine="MAY02")
        out = w.publish()
        self.assertEqual(out["refresh_sent"], ["MAY01", "MAY02"])
        self.assertIn("a", w.lives("MAY01"))
        self.assertNotIn("a", w.lives("MAY02", "u2"))                      # khong co luc 2 may cung phat
        w.clock.t = at(22, 1)
        self.assertNotIn("a", w.lives("MAY01"))
        self.assertIn("a", w.lives("MAY02", "u2"))


class TestChecks(unittest.TestCase):
    def test_capacity_counts_held_occurrence(self):
        w = World(at(20), [sess("a"), sess("b"), sess("c", slots=[])])     # MAY01 toi da 2; a, b dang live 19-22
        w.draft("a", slots=[slot("19:00", "20:30", DAILY)])               # rut ngan -> giu toi 22:00
        w.draft("c", slots=[slot("21:00", "23:00", DAILY)])
        out = w.publish()
        self.assertFalse(out["published"])
        self.assertIn("MAY01", out["errors"][0]["error"])
        self.assertEqual(w.ss.get("a")["slots"][0]["end"], "22:00")        # khong ghi gi
        w2 = World(at(12), [sess("a"), sess("b"), sess("c", slots=[])])    # ban ngay: khong giu -> hop le
        w2.draft("a", slots=[slot("19:00", "20:30", DAILY)])
        w2.draft("c", slots=[slot("21:00", "23:00", DAILY)])
        self.assertTrue(w2.publish()["published"])

    def test_port_clash(self):
        w = World(at(12))
        w.draft("a", obs_port=4455)
        w.draft("b", obs_port=4455)
        out = w.publish()
        self.assertFalse(out["published"])
        self.assertIn("4455", out["errors"][0]["error"])
        self.assertTrue(w.publish(names=["a"])["published"])               # phat hanh rieng 1 phien thi hop le


class TestApp(unittest.TestCase):
    def test_app_edit_published_now_and_draft_goes_stale(self):
        w = World(at(12))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        r = w.app_push("a", [{"days": DAILY, "start": "20:00", "end": "22:00"}], base=0)
        self.assertEqual(r["schedule_version"], 1)
        self.assertEqual((w.sched.log[0]["source"], w.ss.get("a")["published_source"]), (C.PubSource.APP, C.PubSource.APP))
        self.assertEqual(w.ss.get("a")["held_until_ts"], 0)                # app tu ap, khong giu
        self.assertEqual(P.draft_state(w.ss.get("a")), C.DraftState.STALE)
        self.assertEqual(w.cmds.rows, {})                                  # app sua thi khong gui refresh
        with self.assertRaises(C.AiLiveError) as cm:
            w.publish()
        self.assertIn("vừa được đổi lịch", str(cm.exception))
        ResolveDraftService(w.ss, w.clock).execute("op", VIEW, "a", keep=True)
        self.assertEqual(starts(w.lives()["a"]), [("20:00", "22:00")])
        w.publish()
        self.assertEqual(starts(w.lives()["a"]), [("19:30", "22:00")])
        w.ss.rows["b"]["draft"] = {"obs_port": 4470}
        w.ss.rows["b"]["draft_base_version"] = 0
        w.app_push("b", [{"days": DAILY, "start": "08:00", "end": "11:00"}])
        ResolveDraftService(w.ss, w.clock).execute("op", VIEW, "b", keep=False)
        self.assertIsNone(w.ss.get("b")["draft"])

    def test_app_on_stale_base_rejected_same_is_noop(self):
        w = World(at(12))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish()                                                        # ban 1, app chua tai
        with self.assertRaises(C.AiLiveError) as cm:
            w.app_push("a", [{"days": DAILY, "start": "20:00", "end": "22:00"}], base=0)
        self.assertIn("tải lại", str(cm.exception))
        self.assertEqual(w.app_push("a", [{"days": DAILY, "start": "19:30", "end": "22:00"}], base=0)["schedule_version"], 1)
        self.assertEqual(len(w.sched.log), 1)                              # gui y nguyen -> khong tao ban moi
        w.app_push("a", [{"days": DAILY, "start": "20:00", "end": "22:00"}], base=1)
        self.assertEqual(len(w.sched.log), 2)

    def test_app_edit_rejected_while_held(self):
        w = World(at(20))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish()
        with self.assertRaises(C.AiLiveError) as cm:
            w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}])
        self.assertIn("giữ giờ cũ tới 22:00", str(cm.exception))
        w.clock.t = at(22, 5)
        self.assertEqual(w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}])["schedule_version"], 2)

    def test_error_codes_for_app(self):
        """24/10 (hoi cua team app 1.0.28): loi tra ma on dinh trong data.code, khong phai frappe.throw."""
        w = World(at(12))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish()                                                        # ban 1
        with self.assertRaises(C.AiLiveError) as cm:
            w.app_push("a", [{"days": DAILY, "start": "20:00", "end": "22:00"}], base=0)
        self.assertEqual((cm.exception.code, cm.exception.data["schedule_version"]), (C.ErrCode.SCHEDULE_STALE, 1))
        self.assertIn("đã đổi (bản 1)", str(cm.exception))
        w2 = World(at(20))
        w2.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w2.publish()
        with self.assertRaises(C.AiLiveError) as cm:
            w2.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}], base=1)
        self.assertEqual((cm.exception.code, cm.exception.data["held_until"]), (C.ErrCode.SCHEDULE_HELD, at(22)))

    def test_held_serves_old_version_then_stale_after_hold(self):
        """Luc giu gio cu, get_config tra schedule cu + schedule_version CUA BAN CU; het moc giu, app sua tu ban cu
        (base cu) -> schedule_stale, khong ghi de lich moi."""
        w = World(at(12))
        w.draft("a", slots=[slot("19:00", "22:00", DAILY), slot("09:00", "10:00", [6])])
        w.publish()                                                        # ban 1 (doi khung khac, khong giu)
        w.clock.t = at(20)                                                 # a dang live 19-22
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish()                                                        # ban 2, giu toi 22:00
        lv = w.lives()["a"]
        self.assertEqual((starts(lv), lv["held_until"], lv["schedule_version"]), ([("19:00", "22:00"), ("09:00", "10:00")], at(22), 1))
        with self.assertRaises(C.AiLiveError) as cm:                       # dang giu: tu choi du base la gi
            w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}], base=lv["schedule_version"])
        self.assertEqual(cm.exception.code, C.ErrCode.SCHEDULE_HELD)
        w.clock.t = at(22, 5)                                              # het giu, app chua tai lai lich
        with self.assertRaises(C.AiLiveError) as cm:
            w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}], base=1)
        self.assertEqual(cm.exception.code, C.ErrCode.SCHEDULE_STALE)
        self.assertEqual([(x["start"], x["end"]) for x in w.ss.get("a")["slots"]], [("19:30", "22:00")])   # lich moi con nguyen
        lv = w.lives()["a"]
        self.assertEqual((lv["held_until"], lv["schedule_version"]), (None, 2))
        self.assertEqual(w.app_push("a", [{"days": DAILY, "start": "19:30", "end": "23:00"}], base=2)["schedule_version"], 3)

    def test_app_edit_still_checked(self):
        w = World(at(12), [sess("a"), sess("b"), sess("c", slots=[slot("08:00", "10:00", DAILY)])])   # MAY01 toi da 2
        with self.assertRaises(C.AiLiveError) as cm:
            w.app_push("c", [{"days": DAILY, "start": "20:00", "end": "21:00"}])
        self.assertIn("tối đa 2 live", str(cm.exception))
        self.assertEqual(w.sched.log, [])


class TestScreens(unittest.TestCase):
    def test_overview(self):
        w = World(at(20))
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        o = w.overview()
        d = o["drafts"][0]
        self.assertEqual((d["id"], d["state"], d["hold_why"]), ("a", C.DraftState.READY, C.HoldWhy.ON_AIR))
        self.assertIn("giữ tới 22:00", d["hold_text"])
        self.assertEqual(o["machines"][0]["sync"]["tone"], "idle")         # chua tai lich lan nao
        w.config()
        w.publish()
        o = w.overview()
        self.assertEqual(o["machines"][0]["sync"]["tone"], "warn")         # co ban moi chua tai
        self.assertEqual(o["holds"][0]["why_text"], "đang live")
        self.assertEqual(o["versions"][0]["source_text"], "ERP")
        w.config()
        self.assertEqual(w.overview()["machines"][0]["sync"]["tone"], "ok")

    def test_week_overlay_and_held_block(self):
        w = World(at(20))
        w.draft("b", slots=[slot("09:00", "10:00", DAILY)])
        d = WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEW, days=1)
        self.assertEqual(d["days"], ["2026-10-19"])
        b = [x for x in d["blocks"] if x["session"] == "b"][0]
        self.assertEqual((b["start"], b["changed"]), ("09:00", True))
        pub = WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEW, days=1, view="published")
        self.assertEqual([x["start"] for x in pub["blocks"] if x["session"] == "b"], ["08:00"])
        w.draft("a", slots=[slot("19:30", "22:00", DAILY)])
        w.publish(names=["a"])
        d = WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEW, days=2)
        a = [(x["date"], x["start"], x["held"]) for x in d["blocks"] if x["session"] == "a"]
        self.assertEqual(a, [("2026-10-19", "19:00", True), ("2026-10-20", "19:30", False)])
        with self.assertRaises(C.AiLiveError):
            WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEW, days=9)

    def test_month(self):
        w = World(at(12), [sess("a"), sess("b"), sess("c", slots=[slot("20:00", "21:00", d="2026-10-24")])])
        d = MonthScheduleService(w.ss, w.machines, w.clock).execute(VIEW, "2026-10")
        self.assertEqual(len(d["days"]), 35)                               # 28/09 -> 01/11
        day = {x["date"]: x for x in d["days"]}
        self.assertEqual((day["2026-10-24"]["n"], day["2026-10-24"]["over"]), (3, ["MAY01"]))
        self.assertEqual(day["2026-10-23"]["peak"], {"MAY01": 2})
        self.assertEqual(d["over_days"], 1)
        self.assertEqual(d["brand_hours"]["friso"], 31 * 6 + 1)
        with self.assertRaises(C.AiLiveError):
            MonthScheduleService(w.ss, w.machines, w.clock).execute(VIEW, "10/2026")


class TestRules(unittest.TestCase):
    def test_diff_texts(self):
        b = {"slots": [slot("19:00", "22:00", [1, 2, 3, 4, 5]), slot("09:00", "10:00", [6])], "machine": "MAY01", "obs_port": 0}
        a = {"slots": [slot("19:30", "22:00", [1, 2, 3, 4, 5]), slot("20:00", "21:00", d="2026-10-24")], "machine": "MAY02",
             "obs_port": 4455}
        self.assertEqual(P.diff_texts(b, a), ["Chuyển máy MAY01 → MAY02", "Đổi kênh OBS – → 4455", "T2–T6: 19:00–22:00 → 19:30–22:00",
                                              "Thêm khung chỉ 24/10 20:00–21:00", "Bỏ khung T7 09:00–10:00"])

    def test_clock_skew_and_machine_sync(self):
        v = W.heartbeat_vals({"at": at(12) * 1000 + 90000}, [], {}, at(12))
        self.assertEqual(v["hb_clock_skew_s"], 90.0)
        m = {"machine_code": "MAY01", "cfg_version": 2, "cfg_fetched_ts": at(11), "hb_last_seen_ts": at(11, 50)}
        self.assertEqual(P.machine_sync(m, [], at(12), 120)["tone"], "bad")
        self.assertEqual(P.machine_sync(dict(m, hb_last_seen_ts=at(12)), [{"machine": "MAY01", "published_version": 3, "id": "a"}],
                                        at(12), 120)["pending"], ["a"])

    def test_late_hold_needs_change_on_that_occurrence(self):
        s = dict(sess("a"), prev={"slots": [slot("19:00", "22:00", DAILY)], "machine": "MAY01", "obs_port": 0},
                 published_ts=at(18), held_until_ts=0, slots=[slot("19:00", "23:00", DAILY)])
        self.assertEqual(P.late_hold(s, at(17), at(19, 5)), 0)             # chi keo dai -> khong can giu
        s["slots"] = [slot("19:30", "22:00", DAILY)]
        self.assertEqual(P.late_hold(s, at(17), at(19, 5)), at(22))
        self.assertEqual(P.late_hold(s, at(18, 30), at(19, 5)), 0)         # may da tai sau khi phat hanh
        self.assertEqual(P.held_slot(s["prev"], at(22)), {"days": [], "date": "2026-10-19", "start": "19:00", "end": "22:00"})
        self.assertEqual(date.fromisoformat("2026-10-19").isoweekday(), 1)


if __name__ == "__main__":
    unittest.main()
