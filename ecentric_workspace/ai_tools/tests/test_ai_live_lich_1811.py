# Copyright (c) 2026, eCentric and contributors
"""Hop dong lich live 18/11 (ERP la noi DUY NHAT nhap lich): bat / tat tung khung, bat / tat nhieu khung mot luc,
role AI Live Scheduler / Viewer, kieu xem Bang + Timeline 06:00 -> 06:00 kem thuc te, Theo brand trong thang,
va cac sua phia app (server_time dang chuoi gio VN, ma loi o ngoai cung, 503 cho loi tam, off_plan theo may,
gioi han do dai ten). Chay ngoai Frappe.
    python -m pytest -q ecentric_workspace/ai_tools/tests/test_ai_live_lich_1811.py"""
import importlib
import re
import sys
import types
import unittest
from datetime import date
from unittest import mock

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.brand_month_service import BrandMonthService
from ecentric_workspace.ai_tools.features.ai_live.application.copy_week_service import CopyWeekService
from ecentric_workspace.ai_tools.features.ai_live.application.day_board_service import DayBoardService
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService
from ecentric_workspace.ai_tools.features.ai_live.application.toggle_slots_service import ToggleSlotsService
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService
from ecentric_workspace.ai_tools.features.ai_live.application.week_schedule_service import WeekScheduleService
from ecentric_workspace.ai_tools.features.ai_live.domain import board_rules as B
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.tests.test_ai_live_schedule_publish import DAILY, World, at, starts
from ecentric_workspace.ai_tools.tests.test_ai_live_session import FakeMachines, FakeSessions, doc, sess, slot, ts

VIEW = ["EC AI Content"]                       # role cu van xem / sua duoc lich
SCHED, VIEWER, NOBODY = ["AI Live Scheduler"], ["AI Live Viewer"], ["Employee"]


def off(s):
    return dict(s, enabled=False)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class Reports:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.limits = []

    def for_dates(self, dates, limit=2000):
        self.limits.append(limit)
        return [dict(r) for r in self.rows if r["date"] in dates]


class Machines(FakeMachines):
    def sync_states(self):
        return [dict(m) for m in self.rows.values()]


def report(live, machine, day, start, end, **kw):
    """Ban ghi EC AI Live Slot Report da luu (dang repository tra ve)."""
    r = {"live": live, "machine": machine, "brand": "", "date": day, "planned_start_ts": start, "planned_end_ts": end,
         "actual_start_ts": 0.0, "actual_end_ts": 0.0, "start_delay_sec": None, "status": "pending", "start_status": None,
         "interruptions": [], "downtime_sec": 0, "ai_failover_count": 0, "alerts_critical": 0, "note": "", "final": 0,
         "updated_ts": start, "received_ts": start, "off_plan": 0, "session_id": ""}
    r.update(kw)
    return r


# 19/10/2026 = thu Hai. a: 22:00 -> 02:00 moi ngay (qua dem); b: chi 20/10 05:00 -> 07:00 (cat moc 06:00);
# c: 08:00 -> 10:00 moi ngay, may 2, san Shopee, brand vinasoy.
A = sess("a", slots=[slot("22:00", "02:00", DAILY)])
BB = sess("b", slots=[slot("05:00", "07:00", d="2026-10-20")])
CC = sess("c", machine="MAY02", brand="vinasoy", platform="Shopee", slots=[slot("08:00", "10:00", DAILY)])


def board(t, reports=(), roles=VIEW, **kw):
    return DayBoardService(FakeSessions([A, BB, CC]), Reports(reports), Machines(), Clock(t)).execute(roles, **kw)


class TestDayBoard(unittest.TestCase):
    def test_window_0600_to_0600_and_overnight_rows(self):
        d = board(at(9))
        self.assertEqual(d["day"], "2026-10-19")
        self.assertEqual(d["window"], [at(6), at(6, d=20)])
        got = [(r["live"], r["start_ts"]) for r in d["rows"]]
        # a cua 18/10 (22:00 -> 02:00) da xong truoc 06:00 -> khong vao; a 20/10 22:00 thuoc ngay sau
        self.assertEqual(got, [("c", at(8)), ("a", at(22)), ("b", at(5, d=20))])
        self.assertEqual(board(at(3, d=20))["day"], "2026-10-19")          # 03:00 sang van thuoc ngay van hanh hom truoc
        self.assertEqual(board(at(9), day="2026-10-20")["day"], "2026-10-20")

    def test_status_and_no_report_after_15_minutes(self):
        d = board(at(8, 10))
        st = {r["live"]: r["status"] for r in d["rows"]}
        self.assertEqual(st, {"c": "waiting", "a": "upcoming", "b": "upcoming"})
        d = board(at(8, 16))
        c = next(r for r in d["rows"] if r["live"] == "c")
        self.assertEqual((c["status"], c["status_text"], c["no_report"]), ("no_report", "Không có báo cáo", True))
        self.assertEqual(d["counts"]["no_report"], 1)
        rep = report("c", "MAY02", "2026-10-19", at(8), at(10), status="running", start_status="on_time",
                     actual_start_ts=at(8, 1), updated_ts=at(9))
        c = next(r for r in board(at(9), [rep])["rows"] if r["live"] == "c")
        self.assertEqual((c["status"], c["platform"], c["brand"], c["machine_label"], c["hours"]), ("live", "shopee", "vinasoy", "Máy 2", 2.0))
        done = dict(rep, status="on_time", actual_end_ts=at(10), final=1)
        self.assertEqual(next(r for r in board(at(11), [done])["rows"] if r["live"] == "c")["status"], "done")
        missed = dict(rep, status="missed", actual_start_ts=0, final=1)
        self.assertEqual(next(r for r in board(at(11), [missed])["rows"] if r["live"] == "c")["status"], "missed")

    def test_off_plan_report_listed_but_not_counted(self):
        tay = report("tay-tren-may", "MAY01", "2026-10-19", at(12), at(13), off_plan=1, brand="friso", status="on_time",
                     actual_start_ts=at(12), actual_end_ts=at(13), final=1)
        d = board(at(14), [tay])
        row = next(r for r in d["rows"] if r["live"] == "tay-tren-may")
        self.assertTrue(row["off_plan"])
        self.assertEqual(row["chips"][-1]["text"], "Ngoài kế hoạch ERP")
        self.assertEqual(d["counts"]["done"], 0)

    def test_filters_and_facets(self):
        d = board(at(9), platform="SHOPEE")
        self.assertEqual([r["live"] for r in d["rows"]], ["c"])
        self.assertEqual(d["facets"], {"brands": ["friso", "vinasoy"], "machines": ["MAY01", "MAY02"], "platforms": ["shopee", "tiktok"]})
        self.assertEqual([r["live"] for r in board(at(9), brand="friso")["rows"]], ["a", "b"])
        self.assertEqual([r["live"] for r in board(at(9), machine="MAY02")["rows"]], ["c"])

    def test_bad_day_and_roles(self):
        for bad in ("2026-13-01", "19/10/2026", "2026-02-30"):
            with self.assertRaises(C.AiLiveError) as e:
                board(at(9), day=bad)
            self.assertEqual(str(e.exception), C.SessMsg.BAD_DAY)
        self.assertEqual(len(board(at(9), roles=VIEWER)["rows"]), 3)
        self.assertEqual(len(board(at(9), roles=SCHED)["rows"]), 3)
        with self.assertRaises(C.AiLivePermission):
            board(at(9), roles=NOBODY)


class TestBrandMonth(unittest.TestCase):
    def month(self, t, reports=(), **kw):
        sessions = FakeSessions([sess("f", slots=[slot("20:00", "22:00", DAILY)]),
                                 sess("v", brand="vinasoy", slots=[slot("10:00", "11:00", d="2026-10-25")])])
        self.reports = Reports(reports)
        return BrandMonthService(sessions, self.reports, Clock(t)).execute(VIEW, **kw)

    def test_rollup_due_hours_and_off_plan(self):
        reps = [report("f", "MAY01", "2026-10-19", at(20), at(22), status="ended_early", actual_start_ts=at(20),
                       actual_end_ts=at(21), final=1),
                report("tay", "MAY01", "2026-10-19", at(12), at(13), brand="friso", off_plan=1, status="on_time",
                       actual_start_ts=at(12), actual_end_ts=at(13), final=1)]
        d = self.month(at(23), reps, month="2026-10")
        self.assertEqual(d["month"], "2026-10")
        f, v = d["rows"]
        self.assertEqual((f["brand"], f["lives"], f["planned_h"], f["due_h"], f["live_h"], f["off_plan_h"], f["pct"]),
                         ("friso", 31, 62.0, 38.0, 1.0, 1.0, 3))
        self.assertEqual((v["brand"], v["planned_h"], v["due_h"], v["pct"]), ("vinasoy", 1.0, 0.0, None))  # chua toi gio
        self.assertEqual((d["total"]["lives"], d["total"]["planned_h"]), (32, 63.0))
        self.assertEqual(self.reports.limits, [C.MAX_MONTH_REPORTS])

    def test_default_month_platform_filter_and_bad_month(self):
        self.assertEqual(self.month(at(12))["month"], "2026-10")
        d = self.month(at(12), platform="shopee", month="2026-10")
        self.assertEqual((d["rows"], d["total"]["pct"]), ([], None))
        for bad in ("2026-13", "10/2026", "2026-1"):
            with self.assertRaises(C.AiLiveError):
                self.month(at(12), month=bad)


class TestBoardRules(unittest.TestCase):
    def row(self, **rep):
        return {"start_ts": at(19), "end_ts": at(21), "report": rep or None, "no_report": False}

    def test_status_follows_app_slotreport(self):
        self.assertEqual(B.status(self.row(status="overran", actual_start_ts=at(19)), at(21, 30)), "live")   # chua tat
        self.assertEqual(B.status(self.row(status="overran", actual_start_ts=at(19), actual_end_ts=at(21, 20)), at(21, 30)), "done")
        self.assertEqual(B.status(self.row(status="pending"), at(18)), "upcoming")
        self.assertEqual(B.status(self.row(status="pending"), at(19, 5)), "waiting")
        self.assertEqual(B.status(self.row(status="pending"), at(21, 1)), "missed")
        self.assertEqual(B.status(self.row(status="on_time", actual_start_ts=at(19)), at(20)), "live")

    def test_live_seconds(self):
        rep = {"status": "running", "actual_start_ts": at(19), "updated_ts": at(21, 30), "downtime_sec": 120}
        self.assertEqual(B.live_seconds(rep, at(21), at(20)), 3600 - 120)                 # dang chay trong khung
        self.assertEqual(B.live_seconds(rep, at(21), at(23)), 9000 - 120)                 # qua gio: toi lan bao cao cuoi
        self.assertEqual(B.live_seconds({"status": "pending", "actual_start_ts": 0}, at(21), at(23)), 0)
        self.assertEqual(B.live_seconds({"status": "late", "actual_start_ts": at(19, 10), "actual_end_ts": at(21)}, at(21), at(23)), 6600)

    def test_month_days(self):
        days = B.month_days("2026-12", None)
        self.assertEqual((len(days), days[-1].isoformat()), (31, "2026-12-31"))
        self.assertEqual(len(B.month_days("2028-02", None)), 29)


class TestSlotEnabled(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(S.slot_on({}))
        self.assertTrue(S.slot_on({"enabled": ""}))
        self.assertTrue(S.slot_on({"enabled": None}))
        self.assertFalse(S.slot_on({"enabled": 0}))
        self.assertFalse(S.slot_on({"enabled": "false"}))
        sl = S.norm_slots([off(slot("20:00", "22:00", DAILY)), slot("19:00", "21:00", DAILY)])
        self.assertEqual([s["enabled"] for s in sl], [True, False])
        self.assertIsNone(S.self_overlap(sl, date(2026, 10, 19)))                                    # khung tat khong tinh trung
        self.assertIsNotNone(S.self_overlap(S.norm_slots([slot("20:00", "22:00", DAILY), slot("19:00", "21:00", DAILY)]), date(2026, 10, 19)))
        self.assertEqual(S.to_app_schedule(sl), [{"days": DAILY, "start": "19:00", "end": "21:00"}])
        self.assertEqual([o[2] for o in S.occurrences(sl, [date(2026, 10, 19)], include_off=True)], [0, 1])
        self.assertEqual([o[2] for o in S.occurrences(sl, [date(2026, 10, 19)])], [0])

    def test_turn_off_publish_app_gets_only_on_slots(self):
        w = World(at(12))
        r = w.draft("a", slots=[off(slot("19:00", "22:00", DAILY)), slot("06:00", "07:00", [1])])
        self.assertEqual(r["diff"][0], "Tắt khung mỗi ngày 19:00–22:00")
        w.publish()
        self.assertEqual(starts(w.lives()["a"]), [("06:00", "07:00")])
        self.assertEqual([S.slot_on(s) for s in w.ss.get("a")["slots"]], [True, False])
        r = w.draft("a", slots=[slot("19:00", "22:00", DAILY), slot("06:00", "07:00", [1])])
        self.assertEqual(r["diff"], ["Bật lại khung mỗi ngày 19:00–22:00"])

    def test_preserved_counts_only_on_slots(self):
        x = slot("19:00", "22:00", DAILY)
        z = slot("06:00", "07:00", DAILY)
        before = {"machine": "MAY01", "obs_port": 0, "slots": [off(z), x]}
        occ = (at(19), at(22), 1)
        self.assertTrue(P.preserved(occ, before, dict(before, slots=[x])))                # bo khung tat: app van erp1
        before = dict(before, slots=[z, x])
        self.assertFalse(P.preserved(occ, before, dict(before, slots=[off(z), x])))      # tat khung truoc: app danh so lai

    def test_app_push_keeps_erp_off_slots(self):
        w = World(at(12))
        w.ss.rows["a"]["slots"] = S.norm_slots([slot("19:00", "22:00", DAILY), off(slot("06:00", "07:00", [1]))])
        w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "22:00"}], base=0)
        self.assertEqual(w.ss.get("a").get("published_version") or 0, 0)                 # y nguyen -> khong tao ban moi
        w.app_push("a", [{"days": DAILY, "start": "19:00", "end": "23:00"}], base=0)
        got = [(s["start"], s["end"], S.slot_on(s)) for s in w.ss.get("a")["slots"]]
        self.assertEqual(sorted(got), [("06:00", "07:00", False), ("19:00", "23:00", True)])
        self.assertEqual(starts(w.lives()["a"]), [("19:00", "23:00")])

    def test_week_draws_off_block_without_conflict(self):
        w = World(at(12))
        w.draft("a", slots=[off(slot("08:00", "10:00", DAILY))])
        w.draft("b", slots=[slot("08:00", "10:00", DAILY)])
        w.machines.rows["MAY01"]["max_lives"] = 1
        d = WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEW, days=1)
        a = next(x for x in d["blocks"] if x["session"] == "a")
        self.assertEqual((a["slot_on"], a["conflict"], a["key"]), (False, False, "1,2,3,4,5,6,7||08:00|10:00"))
        self.assertFalse(any(x["conflict"] for x in d["blocks"]))


class TestToggleSlots(unittest.TestCase):
    def svc(self, w):
        return ToggleSlotsService(sessions=w.ss, draft=SaveDraftService(w.ss, w.machines, w.clock))

    def test_bulk_off_on_many_sessions(self):
        w = World(at(12))
        items = [{"session": s, "slot": 0, "key": S.slot_key(P.draft_view(w.ss.get(s))["slots"][0])} for s in ("a", "b")]
        r = self.svc(w).execute("op@ec", SCHED, items, 0)
        self.assertEqual((r["changed"], r["errors"]), (2, []))
        self.assertFalse(S.slot_on(P.draft_view(w.ss.get("a"))["slots"][0]))
        self.assertTrue(S.slot_on(w.ss.get("a")["slots"][0]))                            # chi ban nhap - app chua biet
        self.assertEqual(self.svc(w).execute("op@ec", SCHED, items, 0)["changed"], 0)   # bam lai: khong doi gi
        r = self.svc(w).execute("op@ec", SCHED, items, 1)
        self.assertEqual(r["changed"], 2)
        self.assertIsNone(w.ss.get("a").get("draft"))                                    # bat lai = giong ban dang chay

    def test_moved_slot_and_overlap_reported_per_session(self):
        w = World(at(12))
        w.ss.rows["c"] = dict(sess("c"), slots=S.norm_slots([slot("19:00", "21:00", DAILY), off(slot("20:00", "22:00", DAILY))]))
        items = [{"session": "a", "slot": 0, "key": "1,2|x|19:00|22:00"},
                 {"session": "c", "slot": 1, "key": "1,2,3,4,5,6,7||20:00|22:00"},
                 {"session": "zz", "slot": 0, "key": ""}]
        r = self.svc(w).execute("op@ec", VIEW, items, 1)
        errs = {e["session"]: e["error"] for e in r["errors"]}
        self.assertEqual(r["changed"], 0)
        self.assertEqual(errs["a"], C.SessMsg.SLOT_MOVED)
        self.assertIn("trùng", errs["c"])
        self.assertIn("zz", errs)
        self.assertIsNone(w.ss.get("a").get("draft"))

    def test_bad_input_and_roles(self):
        w = World(at(12))
        for bad in (None, [], "[]", [{"session": "a", "slot": "x"}], [{"session": "a", "slot": 0}] * (C.MAX_TOGGLE_SLOTS + 1)):
            with self.assertRaises(C.AiLiveError):
                self.svc(w).execute("op@ec", SCHED, bad, 0)
        with self.assertRaises(C.AiLivePermission):
            self.svc(w).execute("op@ec", VIEWER, [{"session": "a", "slot": 0, "key": ""}], 0)


class TestCopyWeek(unittest.TestCase):
    def world(self):
        w = World(at(12), [sess("a", slots=[slot("19:00", "22:00", DAILY), slot("09:00", "10:00", d="2026-10-21"),
                                             off(slot("11:00", "12:00", d="2026-10-22"))]),
                           sess("b", slots=[slot("08:00", "10:00", DAILY)]),
                           sess("c", slots=[slot("09:00", "10:00", d="2026-10-21"), slot("09:00", "10:00", d="2026-10-28")]),
                           sess("e", machine="MAY02", slots=[slot("09:00", "10:00", d="2026-10-21"), slot("09:30", "10:30", d="2026-10-28")])])
        w.machines.rows["MAY01"]["max_lives"] = 2
        return w

    def svc(self, w):
        return CopyWeekService(w.ss, w.machines, w.clock)

    def test_preview_lists_add_dup_error_and_capacity(self):
        w = self.world()
        d = self.svc(w).execute("op", SCHED, "2026-10-21")                  # ngay bat ky trong tuan -> thu Hai
        self.assertEqual((d["week"], d["to_week"], d["applied"]), ("2026-10-19", "2026-10-26", False))
        it = {i["session"]: i for i in d["items"]}
        self.assertEqual(sorted(it), ["a", "c", "e"])                          # b chi co khung lap hang tuan
        self.assertEqual(it["a"]["add"], ["chỉ 28/10 09:00–10:00", "chỉ 29/10 11:00–12:00 (đang tắt)"])
        self.assertEqual((it["c"]["add"], it["c"]["dup"]), ([], ["chỉ 28/10 09:00–10:00"]))
        self.assertIn("trùng", it["e"]["error"])
        self.assertEqual(d["to_copy"], 2)
        # 28/10 09:00: a (chep) + b + c -> 3 live tren MAY01 toi da 2
        self.assertEqual([(c["machine"], c["ids"]) for c in d["conflicts"]], [("MAY01", ["a", "b", "c"])])
        self.assertIn("tối đa 2 live", d["conflicts"][0]["text"])
        self.assertIsNone(w.ss.get("a").get("draft"))                           # xem truoc khong luu

    def test_apply_saves_drafts_only_for_clean_sessions(self):
        w = self.world()
        d = self.svc(w).execute("op", SCHED, "2026-10-19", apply=True)
        self.assertEqual((d["applied"], d["copied"], d["errors"]), (True, 2, []))
        got = [(x["date"], x["start"], S.slot_on(x)) for x in P.draft_view(w.ss.get("a"))["slots"] if x["date"]]
        self.assertEqual(got, [("2026-10-21", "09:00", True), ("2026-10-22", "11:00", False), ("2026-10-28", "09:00", True),
                               ("2026-10-29", "11:00", False)])
        self.assertIsNone(w.ss.get("e").get("draft"))
        self.assertIsNone(w.ss.get("c").get("draft"))
        self.assertEqual(starts(w.lives()["a"]), [("19:00", "22:00"), ("09:00", "10:00")])   # app chua nhan (nhap)
        again = self.svc(w).execute("op", SCHED, "2026-10-19")
        self.assertEqual({i["session"]: i["add"] for i in again["items"]}["a"], [])          # chep lai: da co het

    def test_roles_and_bad_week(self):
        w = self.world()
        with self.assertRaises(C.AiLivePermission):
            self.svc(w).execute("op", VIEWER, "2026-10-19")
        with self.assertRaises(C.AiLiveError):
            self.svc(w).execute("op", SCHED, "19/10/2026")


class TestRoles(unittest.TestCase):
    def test_scheduler_edits_viewer_only_views(self):
        w = World(at(12))
        SaveDraftService(w.ss, w.machines, w.clock).execute("op", SCHED, "a", slots=[slot("19:30", "22:00", DAILY)])
        with self.assertRaises(C.AiLivePermission):
            SaveDraftService(w.ss, w.machines, w.clock).execute("op", VIEWER, "a", slots=[slot("19:00", "22:00", DAILY)])
        with self.assertRaises(C.AiLivePermission):
            w.pub().execute("op", VIEWER, None, None)
        w.pub().execute("op", SCHED, None, None)
        self.assertEqual(starts(w.lives()["a"]), [("19:30", "22:00")])
        self.assertTrue(WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(VIEWER, days=1)["blocks"])
        with self.assertRaises(C.AiLivePermission):
            WeekScheduleService(w.ss, w.machines, w.clock, w.sched).execute(NOBODY, days=1)


class TestValidateSession(unittest.TestCase):
    def setUp(self):
        self.svc = ValidateSessionService(FakeSessions([]), FakeMachines(), clock=lambda: ts(2026, 10, 19, 12))

    def test_rows_written_back_in_sorted_order(self):
        """Truoc 18/11: sap xep khung xong chi ghi lai thu / gio, quen ngay -> khung 1 ngay nhap truoc bien thanh khung hang tuan."""
        d = doc(rows=[("", "2026-10-24", "09:00", "10:00"), ("1-5", None, "19:00", "22:00")])
        d.slots[1].enabled = 0
        self.svc.execute(d)
        got = [(r.days, r.on_date, r.slot_start, r.enabled) for r in d.slots]
        self.assertEqual(got, [("1,2,3,4,5", None, "19:00", 0), ("", "2026-10-24", "09:00", 1)])

    def test_title_and_shop_length(self):
        for kw, frag in ((dict(title="x" * (C.MAX_SESSION_TITLE + 1)), "80"), (dict(shop_name="s" * (C.MAX_SHOP_NAME + 1)), "120")):
            with self.assertRaises(C.AiLiveError) as e:
                self.svc.execute(doc(**kw))
            self.assertIn(frag, str(e.exception))
        self.svc.execute(doc(title="x" * C.MAX_SESSION_TITLE))


class TestAppFixes(unittest.TestCase):
    def test_server_time_is_vn_text(self):                           # G1: app parseVnTime doc "YYYY-MM-DD HH:MM:SS"
        st = World(at(12, 30)).config()["server_time"]
        self.assertEqual(st, "2026-10-19 12:30:00")
        self.assertTrue(re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", st))

    def test_off_plan_by_machine(self):                              # G4: live ERP ma cua may khac -> ngoai ke hoach
        from ecentric_workspace.ai_tools.tests.test_ai_live_wallboard import SANG, T10, rec
        from ecentric_workspace.ai_tools.tests.test_ai_live_wallboard import World as WallWorld
        w = WallWorld(T10, [SANG])
        w.machines.rows["MAY02"] = {"machine_code": "MAY02", "label": "Máy 2", "enabled": 1, "user": "u2", "brands": "friso"}
        w.report([rec()], user="u2", machine="MAY02")
        self.assertEqual(list(w.reports.rows.values())[0]["off_plan"], 1)
        w.report([rec(planned_start="2026-10-23T04:00:00.000Z")])
        self.assertEqual(sorted(r["off_plan"] for r in w.reports.rows.values()), [0, 1])


def fake_frappe():
    f = types.ModuleType("frappe")
    f.local = types.SimpleNamespace(response={})
    f.db = types.SimpleNamespace(rollback=lambda: None, commit=lambda: None)
    f.errors = []
    f.log_error = lambda title=None, **kw: f.errors.append(title)
    f.whitelist = lambda **kw: (lambda fn: fn)
    f.ValidationError = type("ValidationError", (Exception,), {})
    f.utils = types.SimpleNamespace(strip_html=lambda s: s, cint=int)
    f.session = types.SimpleNamespace(user="u1")
    f.get_roles = lambda user: ["AI Live Viewer"]
    return f


class TestControllerEnvelope(unittest.TestCase):
    def load(self):
        f = fake_frappe()
        wc = types.ModuleType("worker_client")
        wc.WorkerDown = type("WorkerDown", (Exception,), {})
        mods = {"frappe": f, "ecentric_workspace.ai_tools.features.ai_video.infrastructure.worker_client": wc}
        with mock.patch.dict(sys.modules, mods):
            sys.modules.pop("ecentric_workspace.ai_tools.features.ai_live.controllers.api", None)
            api = importlib.import_module("ecentric_workspace.ai_tools.features.ai_live.controllers.api")
        sys.modules.pop("ecentric_workspace.ai_tools.features.ai_live.controllers.api", None)
        return api, f

    def test_code_on_top_and_in_data(self):                          # G2
        api, f = self.load()
        with mock.patch.dict(sys.modules, {"frappe": f}):
            def boom():
                raise C.AiLiveError("cu", C.ErrCode.SCHEDULE_STALE, {"schedule_version": 3})
            out = api._run(boom)
        self.assertEqual((out["success"], out["code"], out["data"]["code"], out["data"]["schedule_version"]),
                         (False, C.ErrCode.SCHEDULE_STALE, C.ErrCode.SCHEDULE_STALE, 3))
        self.assertNotIn("http_status_code", f.local.response)

    def test_unexpected_error_503_only_when_temporary(self):         # G3
        api, f = self.load()
        with mock.patch.dict(sys.modules, {"frappe": f}):
            out = api._run(lambda: 1 / 0)
            self.assertEqual((out["success"], f.local.response.get("http_status_code")), (False, None))
            out = api._run(lambda: 1 / 0, temp_5xx=True)
        self.assertEqual((out["success"], f.local.response.get("http_status_code")), (False, 503))

    def test_viewer_reaches_day_board_endpoint(self):
        api, f = self.load()
        with mock.patch.dict(sys.modules, {"frappe": f}), \
                mock.patch("ecentric_workspace.ai_tools.features.ai_live.application.day_board_service.DayBoardService.__init__",
                           lambda self, **kw: (setattr(self, "sessions", FakeSessions([A])), setattr(self, "reports", Reports()),
                                               setattr(self, "machines", Machines()), setattr(self, "clock", Clock(at(9))))[0]):
            out = api.day_board(day="2026-10-19", platform="tiktok")
        self.assertTrue(out["success"], out)
        self.assertEqual([r["live"] for r in out["data"]["rows"]], ["a"])


if __name__ == "__main__":
    unittest.main()
