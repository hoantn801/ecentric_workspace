# Copyright (c) 2026, eCentric and contributors
"""Phien live + Lich live (fix10d): khung gio, trung gio, suc chua may, trang thai, lich tuan, lenh cho app,
chi tiet phien qua tin hieu, tong ket cuoi phien, get_config.lives - chay ngoai Frappe."""
import base64
import types
import unittest
from datetime import date, datetime, timedelta, timezone

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.ack_command_service import AckCommandService
from ecentric_workspace.ai_tools.features.ai_live.application.get_config_service import GetConfigService
from ecentric_workspace.ai_tools.features.ai_live.application.list_sessions_service import ListSessionsService
from ecentric_workspace.ai_tools.features.ai_live.application.pull_commands_service import PullCommandsService
from ecentric_workspace.ai_tools.features.ai_live.application.push_heartbeat_service import PushHeartbeatService
from ecentric_workspace.ai_tools.features.ai_live.application.push_session_summary_service import PushSessionSummaryService
from ecentric_workspace.ai_tools.features.ai_live.application.push_slots_service import PushSlotsService
from ecentric_workspace.ai_tools.features.ai_live.application.queue_command_service import QueueCommandService
from ecentric_workspace.ai_tools.features.ai_live.application.save_slots_service import SaveSlotsService
from ecentric_workspace.ai_tools.features.ai_live.application.session_detail_service import SessionDetailService
from ecentric_workspace.ai_tools.features.ai_live.application.session_history_service import SessionHistoryService
from ecentric_workspace.ai_tools.features.ai_live.application.set_sessions_enabled_service import SetSessionsEnabledService
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService
from ecentric_workspace.ai_tools.features.ai_live.application.viewer_wall_service import ViewerWallService, pick_source
from ecentric_workspace.ai_tools.features.ai_live.application.week_schedule_service import WeekScheduleService
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import FakeAlerts, FakeHealth, FakeSamples, FakeSettings, FakeThumbs

VN = timezone(timedelta(hours=7))
VIEW, NOBODY = ["EC AI Content"], ["Employee"]
JPG = b"\xff\xd8\xff\xe0" + b"x" * 40


def ts(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=VN).timestamp()


# 2026-10-19 la thu Hai
MON = ts(2026, 10, 19, 12)


def slot(start, end, days=None, d=None):
    return {"days": days if days is not None else [], "date": d, "start": start, "end": end}


class FakeMachines:
    def __init__(self):
        self.rows = {"MAY01": {"machine_code": "MAY01", "label": "Máy 1", "enabled": 1, "user": "u1", "brands": "friso\nwilmar",
                               "max_lives": 2},
                     "MAY02": {"machine_code": "MAY02", "label": "Máy 2", "enabled": 1, "user": "u2", "brands": "friso", "max_lives": 2}}

    def by_user(self, user):
        return next((dict(m) for m in self.rows.values() if m["user"] == user), None)

    def get(self, code):
        return self.rows.get(code)

    def all(self):
        return list(self.rows.values())


class FakeSessions:
    def __init__(self, rows=()):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.saved = []

    def list(self, filters=None):
        return [dict(r) for _, r in sorted(self.rows.items())]

    def get(self, name):
        r = self.rows.get(name)
        return dict(r) if r else None

    def by_machine(self, machine):
        return [dict(r) for r in self.rows.values() if r["machine"] == machine]

    def save_slots(self, name, slots):
        self.rows[name]["slots"] = slots
        self.saved.append(name)

    def set_enabled(self, names, enabled):
        for n in names:
            if n == "boom":
                raise C.AiLiveError("Máy MAY01 chỉ chạy tối đa 2 live")
            self.rows[n]["enabled"] = int(enabled)
        return list(names)


def sess(sid, machine="MAY01", brand="friso", slots=None, enabled=1, **kw):
    d = {"id": sid, "title": sid.upper(), "brand": brand, "platform": "TikTok", "shop_name": "", "tiktok_username": "shop",
         "machine": machine, "obs_port": 0, "kit": "", "mode": "", "auto_obs_start": 0, "enabled": enabled,
         "updated_at": "2026-10-18", "slots": slots if slots is not None else [slot("19:00", "22:00", [1, 2, 3, 4, 5, 6, 7])]}
    d.update(kw)
    return d


class FakeCommands:
    def __init__(self):
        self.rows, self.n = {}, 0

    def insert(self, row):
        self.n += 1
        cid = "c%d" % self.n
        self.rows[cid] = dict(row, id=cid, status=C.CMD_QUEUED, sent_ts=0, done_ts=0, result="", args=row.get("args") or {})
        return cid

    def pending(self, machine):
        return [dict(r) for r in self.rows.values() if r["machine"] == machine and r["status"] == C.CMD_QUEUED]

    def get(self, cid):
        r = self.rows.get(cid)
        return dict(r) if r else None

    def set_status(self, cid, status, ts_field=None, ts=None, result=None):
        self.rows[cid]["status"] = status
        if ts_field:
            self.rows[cid][ts_field] = ts
        if result is not None:
            self.rows[cid]["result"] = result

    def recent(self, live, since, limit=20):
        return [dict(r) for r in self.rows.values() if r["live"] == live and r["created_ts"] >= since][:limit]


class FakeLogs:
    def __init__(self):
        self.rows = {}

    def upsert(self, key, row):
        self.rows[key] = dict(row, log_key=key, **row["counters"])
        return key

    def list(self, since, live=None, brand=None, limit=500):
        out = [dict(r) for r in self.rows.values() if r["started_ts"] >= since and (not live or r["live"] == live)
               and (not brand or r["brand"] == brand)]
        return sorted(out, key=lambda r: -r["started_ts"])[:limit]


class Doc(types.SimpleNamespace):
    pass


def doc(**kw):
    rows = [Doc(days=d, on_date=od, slot_start=a, slot_end=b) for d, od, a, b in kw.pop("rows", [("1-5", None, "19:00", "22:00")])]
    base = dict(live_id="friso_tt", name=None, platform="TikTok", tiktok_username="@friso.vn", mode="", machine="MAY01",
                brand="friso", obs_port=4455, enabled=1, slots=rows, watch_url="", phone_serial="")
    base.update(kw)
    return Doc(**base)


class TestSlotRules(unittest.TestCase):
    def test_norm_and_errors(self):
        out = S.norm_slots([{"days": "1-5", "start": "19:00", "end": "22:00"}, {"days": "", "start": "22:00", "end": "02:00"},
                            {"date": "2026-10-24", "start": "09:00", "end": "11:00"}])
        self.assertEqual(out[0]["days"], [1, 2, 3, 4, 5])
        self.assertEqual(out[1]["days"], list(range(1, 8)))
        self.assertEqual((out[2]["date"], out[2]["days"]), ("2026-10-24", []))
        for bad in ({"start": "7pm", "end": "22:00"}, {"start": "19:00", "end": "19:00"}, {"days": "8", "start": "19:00", "end": "20:00"},
                    {"date": "24/10/2026", "start": "09:00", "end": "10:00"}):
            with self.assertRaises(C.AiLiveError) as e:
                S.norm_slots([{"start": "08:00", "end": "09:00"}, bad])
            self.assertIn("Khung giờ 2", str(e.exception))

    def test_overlap_overnight_and_date(self):
        today = date(2026, 10, 19)
        a = S.norm_slots([{"days": "1-7", "start": "22:00", "end": "02:00"}, {"days": "2", "start": "01:00", "end": "03:00"}])
        self.assertEqual(S.self_overlap(a, today), [1, 2])                     # qua dem tu thu Hai trung 01:00 thu Ba
        b = S.norm_slots([{"days": "1-5", "start": "19:00", "end": "22:00"}, {"date": "2026-11-07", "start": "20:00", "end": "21:00"}])
        self.assertIsNone(S.self_overlap(b, today))                           # 07/11 la thu Bay
        c = S.norm_slots([{"days": "1-5", "start": "19:00", "end": "22:00"}, {"date": "2026-11-06", "start": "21:00", "end": "23:00"}])
        self.assertEqual(S.self_overlap(c, today), [1, 2])                     # 06/11 thu Sau

    def test_capacity(self):
        today = date(2026, 10, 19)
        grp = [{"id": "a", "slots": S.norm_slots([{"start": "19:00", "end": "22:00"}])},
               {"id": "b", "slots": S.norm_slots([{"start": "20:00", "end": "23:00"}])},
               {"id": "c", "slots": S.norm_slots([{"days": "3", "start": "21:00", "end": "21:30"}])}]
        self.assertEqual(S.capacity_conflicts(grp[:2], 2, today), [])
        bad = S.capacity_conflicts(grp, 2, today)
        self.assertTrue(bad and set(bad[0]["ids"]) == {"a", "b", "c"})
        self.assertEqual(S.capacity_conflicts(grp, 3, today), [])

    def test_windows_and_health_date_slot(self):
        sl = S.norm_slots([{"days": "1", "start": "22:00", "end": "02:00"}, {"date": "2026-10-21", "start": "09:00", "end": "10:00"}])
        self.assertIsNotNone(S.window_now(sl, ts(2026, 10, 20, 1, 30)))      # qua dem tu thu Hai
        self.assertIsNone(S.window_now(sl, ts(2026, 10, 20, 2, 30)))
        self.assertEqual(S.next_window(sl, ts(2026, 10, 20, 3))[0], ts(2026, 10, 21, 9))
        hs = R.sanitize_schedule(S.to_app_schedule(sl))
        self.assertEqual(hs[1]["date"], "2026-10-21")
        self.assertTrue(R.in_schedule(hs, ts(2026, 10, 21, 9, 30)))
        self.assertFalse(R.in_schedule(hs, ts(2026, 10, 28, 9, 30)))        # khung 1 ngay khong lap tuan sau

    def test_sanitize_detail(self):
        raw = {"now": {"kind": "main", "product": "Gold 4", "file": "a.mp4", "started_at": MON, "ends_at": MON + 30, "x": 1},
               "next": [{"kind": "main", "product": "P%d" % i, "eta_s": i} for i in range(15)],
               "queue": [{"user": "Lan", "question": "giá?" * 100, "state": "waiting"}], "recent": "bad",
               "counters": {"comments": 12, "answered": "3", "zzz": 9}, "cost_today_usd": 1.23456,
               "platform": {"status": "live", "viewers": "57", "likes": 3}}
        d = S.sanitize_detail(raw, MON)
        self.assertEqual(len(d["next"]), C.DETAIL_LIMITS["next"])
        self.assertLessEqual(len(d["queue"][0]["question"]), C.MAX_DETAIL_TEXT)
        self.assertEqual(d["recent"], [])
        self.assertEqual(d["counters"], {"comments": 12, "answered": 3})
        self.assertEqual(d["platform"]["viewers"], 57)
        self.assertNotIn("x", d["now"])
        self.assertIsNone(S.sanitize_detail("bad", MON))


class TestValidateSession(unittest.TestCase):
    def setUp(self):
        self.sessions = FakeSessions([sess("a", obs_port=4455, slots=S.norm_slots([{"start": "19:00", "end": "22:00"}])),
                                      sess("b", obs_port=4456, slots=S.norm_slots([{"start": "20:00", "end": "23:00"}]))])
        self.svc = ValidateSessionService(self.sessions, FakeMachines(), clock=lambda: MON)

    def test_ok_normalizes(self):
        d = doc(machine="MAY02", obs_port=4455)
        self.svc.execute(d)
        self.assertEqual(d.tiktok_username, "friso.vn")
        self.assertEqual(d.slots[0].days, "1,2,3,4,5")

    def test_errors(self):
        cases = [(dict(live_id="bad id!"), "Mã phiên"), (dict(platform="Lazada"), "Sàn"), (dict(tiktok_username=""), "username"),
                 (dict(machine="MAY02", brand="wilmar"), "chưa giao"), (dict(obs_port=4456), "Cổng OBS 4456"),
                 (dict(obs_port=80), "1024"), (dict(mode="turbo"), "Chế độ"),
                 (dict(watch_url="http://shopee.vn/x"), "https://"), (dict(phone_serial="a b"), "điện thoại"),
                 (dict(rows=[("1", None, "19:00", "21:00"), ("1", None, "20:00", "22:00")]), "trùng với khung 1"),
                 (dict(obs_port=4460), "tối đa 2 live")]
        for kw, msg in cases:
            with self.assertRaises(C.AiLiveError, msg=kw) as e:
                self.svc.execute(doc(**kw))
            self.assertIn(msg, str(e.exception))

    def test_disabled_skips_capacity(self):
        self.svc.execute(doc(obs_port=4460, enabled=0))


class TestListDetailWeek(unittest.TestCase):
    def setUp(self):
        self.health = FakeHealth()
        self.sessions = FakeSessions([sess("a"), sess("b", slots=S.norm_slots([{"start": "08:00", "end": "09:00"}])),
                                      sess("c", enabled=0), sess("d", machine="MAY02", slots=S.norm_slots([{"start": "11:30", "end": "13:00"}]))])
        now = MON
        self.health.upsert("MAY01__b", {"machine": "MAY01", "live": "b", "brand": "friso", "state": "idle", "last_seen_ts": now - 30,
                                        "metrics": {}, "alerts": [], "schedule": [], "detail": {}})
        self.health.upsert("MAY01__a", {"machine": "MAY01", "live": "a", "brand": "friso", "state": "idle", "last_seen_ts": now - 30,
                                        "metrics": {}, "alerts": [], "schedule": [],
                                        "detail": {"platform": {"viewers": 40}, "cost_today_usd": 0.5, "now": {"product": "Gold 4"}}})
        self.health.upsert("MAY02__d", {"machine": "MAY02", "live": "d", "brand": "friso", "state": "live", "last_seen_ts": now - 20,
                                        "metrics": {"streaming": True}, "alerts": [], "schedule": [], "detail": {}})

    def test_list_statuses_and_filters(self):
        svc = ListSessionsService(self.sessions, self.health, FakeSettings(), FakeMachines(), clock=lambda: MON)
        d = svc.execute(VIEW)
        st = {r["id"]: r["status"] for r in d["sessions"]}
        self.assertEqual(st, {"a": "scheduled", "b": "scheduled", "c": "off", "d": "on_air"})
        self.assertEqual(d["counts"]["total"], 4)
        a = next(r for r in d["sessions"] if r["id"] == "a")
        self.assertEqual((a["viewers"], a["cost_today_usd"], a["now_playing"]), (40, 0.5, "Gold 4"))
        self.assertEqual([r["id"] for r in svc.execute(VIEW, machine="MAY02")["sessions"]], ["d"])
        self.assertEqual([r["id"] for r in svc.execute(VIEW, status="off")["sessions"]], ["c"])
        with self.assertRaises(C.AiLivePermission):
            svc.execute(NOBODY)

    def test_problem_when_in_window_without_signal(self):
        svc = ListSessionsService(self.sessions, self.health, FakeSettings(), FakeMachines(), clock=lambda: ts(2026, 10, 19, 20))
        rows = {r["id"]: r for r in svc.execute(VIEW)["sessions"]}
        self.assertEqual(rows["a"]["status"], "problem")                     # 20:00 trong lich, tin hieu cu 8 gio
        self.assertEqual(rows["a"]["level"], C.Level.OFF)

    def test_detail(self):
        cmds, logs = FakeCommands(), FakeLogs()
        cmds.insert({"live": "a", "machine": "MAY01", "action": "pause_ai", "args": {}, "created_ts": MON - 60})
        svc = SessionDetailService(self.sessions, self.health, FakeSamples(), FakeAlerts(), FakeSettings(), cmds,
                                   clock=lambda: MON, logs=logs)
        d = svc.execute(VIEW, "a")
        self.assertEqual(d["detail"]["now"]["product"], "Gold 4")
        self.assertEqual(len(d["commands"]), 1)
        self.assertEqual(set(d["thumbs"]), set(C.THUMB_KINDS))
        with self.assertRaises(C.AiLiveError):
            svc.execute(VIEW, "zzz")

    def test_week_conflicts(self):
        self.sessions.rows["e"] = sess("e", slots=S.norm_slots([{"date": "2026-10-21", "start": "20:00", "end": "21:00"}]))
        self.sessions.rows["f"] = sess("f", slots=S.norm_slots([{"date": "2026-10-21", "start": "20:30", "end": "21:30"}]))
        d = WeekScheduleService(self.sessions, FakeMachines(), clock=lambda: MON).execute(VIEW, "2026-10-22")
        self.assertEqual(d["week"], "2026-10-19")
        self.assertEqual(len(d["days"]), 7)
        hit = [b for b in d["blocks"] if b["conflict"]]
        self.assertTrue(hit and {b["session"] for b in hit} >= {"a", "e", "f"} and all(b["date"] == "2026-10-21" for b in hit))
        self.assertEqual(len([b for b in d["blocks"] if b["session"] == "a"]), 7)
        with self.assertRaises(C.AiLiveError):
            WeekScheduleService(self.sessions, FakeMachines(), clock=lambda: MON).execute(VIEW, "22/10/2026")


class TestEditAndCommands(unittest.TestCase):
    def test_save_slots_and_bulk(self):
        ss = FakeSessions([sess("a"), sess("b")])
        r = SaveSlotsService(ss).execute(VIEW, "a", '[{"days":"6,7","start":"09:00","end":"11:00"}]')
        self.assertEqual(r["session"]["slots"][0]["days"], [6, 7])
        with self.assertRaises(C.AiLiveError):
            SaveSlotsService(ss).execute(VIEW, "a", [{"start": "9h", "end": "11:00"}])
        ss.rows["boom"] = sess("boom")
        d = SetSessionsEnabledService(ss).execute(VIEW, '["a","boom","b"]', False)
        self.assertEqual((d["done"], [e["id"] for e in d["errors"]]), (["a", "b"], ["boom"]))

    def test_command_flow(self):
        ss, cmds = FakeSessions([sess("a"), sess("x", machine="")]), FakeCommands()
        clock = types.SimpleNamespace(t=MON)
        q = QueueCommandService(ss, cmds, clock=lambda: clock.t)
        cid = q.execute("op@ec", VIEW, "a", "play_faq", '{"topic":"Giá"}')["id"]
        old = q.execute("op@ec", VIEW, "a", "pause_ai")["id"]
        cmds.rows[old]["created_ts"] = MON - C.CMD_TTL_S - 5
        for bad in (("a", "reboot", None), ("a", "play_faq", "{}"), ("x", "pause_ai", None), ("zz", "pause_ai", None)):
            with self.assertRaises(C.AiLiveError):
                q.execute("op@ec", VIEW, *bad)
        pull = PullCommandsService(FakeMachines(), cmds, clock=lambda: clock.t)
        got = pull.execute("u1", "MAY01")["commands"]
        self.assertEqual([(c["id"], c["action"], c["args"]) for c in got], [(cid, "play_faq", {"topic": "Giá"})])
        self.assertEqual(cmds.rows[old]["status"], C.CMD_EXPIRED)
        self.assertEqual(pull.execute("u1", "MAY01")["commands"], [])          # da Sent
        ack = AckCommandService(FakeMachines(), cmds, clock=lambda: clock.t)
        with self.assertRaises(C.AiLivePermission):
            ack.execute("u2", "MAY02", cid, True)
        self.assertEqual(ack.execute("u1", "MAY01", cid, False, "không có FAQ Giá")["status"], C.CMD_FAILED)
        with self.assertRaises(C.AiLivePermission):
            pull.execute("someone", "MAY01")


class TestHeartbeatSummaryConfig(unittest.TestCase):
    def test_heartbeat_detail_platform_thumb_and_summary(self):
        health, thumbs, logs = FakeHealth(), FakeThumbs(), FakeLogs()
        machines = FakeMachines()
        summ = PushSessionSummaryService(machines, logs, clock=lambda: MON)
        svc = PushHeartbeatService(machines, health, FakeSamples(), thumbs, clock=lambda: MON, summaries=summ)
        lv = {"live": "a", "brand": "friso", "state": "live", "metrics": {"fps": 30},
              "detail": {"now": {"kind": "main", "product": "Gold 4"}, "counters": {"comments": 5}},
              "platform_thumb_b64": base64.b64encode(JPG).decode(),
              "session_summary": {"session": "a-20261019-1900", "started_at": MON - 3600, "ended_at": MON, "counters": {"comments": 50, "answered": 20},
                                  "cost_usd": 0.42, "reason": "schedule_end"}}
        r = svc.execute("u1", {"machine": "MAY01", "lives": [lv]})
        self.assertEqual((r["saved"], r["skipped"]), (["a"], []))
        row = health.get("MAY01__a")
        self.assertEqual(row["detail"]["now"]["product"], "Gold 4")
        self.assertEqual(row["platform_thumb_ts"], MON)
        self.assertIn(("MAY01__a", "platform"), thumbs.files)
        self.assertEqual(len(logs.rows), 1)
        svc.execute("u1", {"machine": "MAY01", "lives": [dict(lv, detail=None)]})
        self.assertEqual(len(logs.rows), 1)                                   # gui lai cung ma phien -> ghi de
        self.assertEqual(health.get("MAY01__a")["detail"], {})
        bad = svc.execute("u1", {"machine": "MAY01", "lives": [dict(lv, session_summary={"session": "x"})]})
        self.assertIn("tổng kết phiên", bad["skipped"][0]["why"])

    def test_summary_api_and_history(self):
        logs = FakeLogs()
        svc = PushSessionSummaryService(FakeMachines(), logs, clock=lambda: MON)
        for i, (live, brand) in enumerate((("a", "friso"), ("a", "friso"), ("w", "wilmar"))):
            svc.execute("u1", "MAY01", live, brand, {"session": "s%d" % i, "started_at": MON - 7200 * (i + 1), "duration_s": 3600,
                                                     "counters": {"comments": 10, "answered": 4, "greeted": 2}, "cost_usd": 0.5})
        with self.assertRaises(C.AiLiveError):
            svc.execute("u1", "MAY01", "a", "nestle", {"session": "z", "started_at": MON})
        with self.assertRaises(C.AiLiveError):
            svc.execute("u1", "MAY01", "a", "friso", {"session": "z", "started_at": MON + 9999})
        h = SessionHistoryService(logs, clock=lambda: MON).execute(VIEW, live="a")
        self.assertEqual(h["totals"]["runs"], 2)
        self.assertEqual((h["totals"]["hours"], h["totals"]["comments"], h["totals"]["cost_usd"]), (2.0, 20, 1.0))
        self.assertEqual(SessionHistoryService(logs, clock=lambda: MON).execute(VIEW, days=999)["days"], C.MAX_HISTORY_DAYS)

    def test_get_config_lives(self):
        from ecentric_workspace.ai_tools.tests.test_ai_live_service import FakeBrands
        ss = FakeSessions([sess("a", mode="lite", obs_port=4455), sess("b", enabled=0), sess("d", machine="MAY02"),
                           sess("e", slots=S.norm_slots([{"date": "2026-10-21", "start": "09:00", "end": "10:00"}]))])
        machines = FakeMachines()
        d = GetConfigService(machines, FakeBrands(), sessions=ss).execute("u1", "MAY01")
        self.assertEqual([lv["id"] for lv in d["lives"]], ["a", "e"])
        a, e = d["lives"]
        self.assertEqual((a["mode"], a["mode_override"], a["obs_port"]), ("lite", "lite", 4455))
        self.assertEqual(e["mode"], "full")                                   # theo brand friso
        self.assertEqual(e["schedule"], [{"days": list(range(1, 8)), "start": "09:00", "end": "10:00", "date": "2026-10-21"}])
        self.assertEqual((a["watch_url"], a["phone_serial"]), ("", ""))
        self.assertEqual(d["max_lives"], 2)


class TestPushSlots(unittest.TestCase):
    """App gui lai khung gio cua 1 phien tren may minh (lich 2 chieu)."""
    APP = [{"days": [1, 2, 3, 4, 5], "start": "19:00", "end": "22:00"}, {"days": "6-7", "start": "22:00", "end": "02:00"},
           {"days": list(range(1, 8)), "date": "2026-10-25", "start": "09:00", "end": "10:30"}]

    def setUp(self):
        self.ss = FakeSessions([sess("a"), sess("d", machine="MAY02"), sess("n", brand="nestle"), sess("off", enabled=0)])
        self.svc = PushSlotsService(FakeMachines(), self.ss)

    def test_success_round_trip_with_get_config(self):
        import json
        r = self.svc.execute("u1", "MAY01", "a", json.dumps(self.APP))
        self.assertEqual(self.ss.saved, ["a"])
        self.assertEqual(r["session"]["id"], "a")
        self.assertEqual(r["session"]["slots"], r["slots"])
        self.assertEqual(r["slots"][2], {"days": [], "date": "2026-10-25", "start": "09:00", "end": "10:30"})
        self.assertEqual(r["schedule"][1], {"days": [6, 7], "start": "22:00", "end": "02:00"})
        from ecentric_workspace.ai_tools.tests.test_ai_live_service import FakeBrands
        lv = GetConfigService(FakeMachines(), FakeBrands(), sessions=self.ss).execute("u1", "MAY01")["lives"][0]
        self.assertEqual(lv["schedule"], r["schedule"])                       # app keo ve dung cai vua gui
        self.svc.execute("u1", "MAY01", "a", lv["schedule"])                  # gui lai schedule cua get_config -> y nguyen
        self.assertEqual(self.ss.get("a")["slots"], r["slots"])
        self.assertEqual(self.svc.execute("u1", "MAY01", "off", [])["slots"], [])   # phien dang tat van luu duoc; [] = xoa het

    def test_same_normalization_as_save_slots(self):
        other = FakeSessions([sess("a")])
        SaveSlotsService(other).execute(VIEW, "a", self.APP)
        self.svc.execute("u1", "MAY01", "a", self.APP)
        self.assertEqual(self.ss.get("a")["slots"], other.get("a")["slots"])
        for bad in ([{"start": "9h", "end": "11:00"}], [{"days": "8", "start": "09:00", "end": "10:00"}]):
            with self.assertRaises(C.AiLiveError) as cm:
                self.svc.execute("u1", "MAY01", "a", bad)
            self.assertIn("Khung giờ 1", str(cm.exception))
        for bad in (None, "", '{"start":"09:00"}', "not json"):
            with self.assertRaises(C.AiLiveError):
                self.svc.execute("u1", "MAY01", "a", bad)                     # khong tu xoa lich khi thieu slots
        self.assertEqual(self.ss.saved, ["a"])

    def test_unknown_live_or_brand_for_machine(self):
        for live in ("d", "zz", "", "a b"):                                   # d thuoc MAY02
            with self.assertRaises(C.AiLiveError) as cm:
                self.svc.execute("u1", "MAY01", live, self.APP)
            self.assertNotIsInstance(cm.exception, C.AiLivePermission)
        with self.assertRaises(C.AiLiveError) as cm:
            self.svc.execute("u1", "MAY01", "zz", self.APP)
        self.assertIn("không thuộc máy MAY01", str(cm.exception))
        with self.assertRaises(C.AiLiveError) as cm:
            self.svc.execute("u1", "MAY01", "n", self.APP)                    # brand nestle chua giao cho MAY01
        self.assertIn("nestle", str(cm.exception))
        self.assertEqual(self.ss.saved, [])

    def test_machine_token_mismatch(self):
        for user, code in (("u2", "MAY01"), ("u1", "MAY02"), ("u1", ""), ("someone", "MAY01")):
            with self.assertRaises(C.AiLivePermission):
                self.svc.execute(user, code, "a", self.APP)
        self.assertEqual(self.svc.execute("u2", "MAY02", "d", self.APP)["session"]["id"], "d")
        self.assertEqual(self.ss.saved, ["d"])


class TestViewerWall(unittest.TestCase):
    def test_pick_source_priority_and_stale(self):
        now = MON
        self.assertEqual(pick_source({"platform_thumb_ts": now - 6, "stream_thumb_ts": now - 2, "phone_thumb_ts": now - 1}, now),
                         ("platform", now - 6))
        self.assertEqual(pick_source({"platform_thumb_ts": now - 500, "phone_thumb_ts": now - 40}, now), ("phone", now - 40))
        self.assertEqual(pick_source({"platform_thumb_ts": now - 500, "phone_thumb_ts": now - 900}, now), ("platform", now - 500))
        self.assertEqual(pick_source({}, now), (None, 0))

    def test_wall_only_on_air(self):
        health = FakeHealth()
        ss = FakeSessions([sess("a", watch_url="https://live.shopee.vn/share?id=1", platform="Shopee"),
                           sess("b", slots=S.norm_slots([{"start": "08:00", "end": "09:00"}])), sess("c", enabled=0)])
        at = ts(2026, 10, 19, 20)
        health.upsert("MAY01__a", {"machine": "MAY01", "live": "a", "brand": "friso", "state": "live", "last_seen_ts": at - 10,
                                   "metrics": {}, "alerts": [], "schedule": [], "detail": {"platform": {"viewers": 9}},
                                   "platform_thumb_ts": at - 200, "phone_thumb_ts": at - 30})
        d = ViewerWallService(ss, health, FakeSettings(), clock=lambda: at).execute(VIEW)
        self.assertEqual([t["id"] for t in d["tiles"]], ["a"])
        t = d["tiles"][0]
        self.assertEqual((t["source"], t["age_s"], t["stale"], t["viewers"]), ("phone", 30, False, 9))
        self.assertTrue(t["watch_url"].startswith("https://"))
        with self.assertRaises(C.AiLivePermission):
            ViewerWallService(ss, health, FakeSettings(), clock=lambda: at).execute(NOBODY)


if __name__ == "__main__":
    unittest.main()
