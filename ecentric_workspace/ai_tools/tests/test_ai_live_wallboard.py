# Copyright (c) 2026, eCentric and contributors
"""fix10h - Truc live: push_slot_report (A8, T24-T27), ke hoach vs thuc te (B3 / 11.3), wallboard (B2: bo dem,
thu tu the, may mat lien lac, chi phi so voi tran, AI chinh / du phong, live cho gio), lenh 1 cham. Chay ngoai Frappe."""
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.push_slot_report_service import PushSlotReportService
from ecentric_workspace.ai_tools.features.ai_live.application.queue_command_service import CommandStatusService, QueueCommandService
from ecentric_workspace.ai_tools.features.ai_live.application.schedule_actuals_service import ScheduleActualsService
from ecentric_workspace.ai_tools.features.ai_live.application.wallboard_service import WallboardService
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import slot_report_rules as SR
from ecentric_workspace.ai_tools.tests.test_ai_live_machine_watch import World as WatchWorld
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import VIEW, live, vn_ts
from ecentric_workspace.ai_tools.tests.test_ai_live_session import FakeCommands, FakeSessions, sess, slot

T10 = vn_ts(2026, 10, 23, 10, 0)          # thu Sau 23/10 10:00 gio VN = 03:00Z
ISO10 = "2026-10-23T03:00:00.000Z"


class FakeReports:
    def __init__(self):
        self.rows = {}

    def upsert(self, key, row):
        self.rows[key] = dict(self.rows.get(key) or {}, **row)

    def for_dates(self, dates):
        return [dict(r) for r in self.rows.values() if r["date"] in dates]

    def purge(self, before):
        pass


class Costs:
    def __init__(self, day=None):
        self.day = day or {}

    def day_total(self, brand, date):
        return self.day.get(brand, 0)


class Brands:
    def get(self, brand):
        return {"friso": {"daily_cost_cap_usd": 5}}.get(brand)


class Cmds(FakeCommands):
    def since(self, ts, limit=500):
        return sorted([dict(r) for r in self.rows.values() if r["created_ts"] >= ts], key=lambda r: -r["created_ts"])

    def many(self, ids):
        return [dict(r) for i, r in self.rows.items() if i in ids]


class World(WatchWorld):
    def __init__(self, t0, sessions=(), **kw):
        super().__init__(t0, **kw)
        self.sess = FakeSessions(sessions)
        self.sessions = self.sess                    # may im lang dung chung lich ERP
        self.reports, self.cmds, self.costs = FakeReports(), Cmds(), Costs()
        self.machines.get = lambda code: self.machines.rows.get(code)

    def report(self, slots, user="u1", machine="MAY01"):
        return PushSlotReportService(self.machines, self.reports, self.sess, self.clock).execute(user, machine, slots)

    def actuals(self, day=None):
        return ScheduleActualsService(self.sess, self.reports, self.clock).execute(VIEW, day)

    def wall(self, **kw):
        return WallboardService(self.health, self.machines, self.sess, self.settings, self.incidents, self.cmds, self.costs,
                                Brands(), ScheduleActualsService(self.sess, self.reports, self.clock), self.clock).execute(VIEW, **kw)


def rec(**kw):
    d = {"live": "friso-sang", "brand": "friso", "date": "2026-10-23", "planned_start": ISO10,
         "planned_end": "2026-10-23T05:00:00.000Z", "actual_start": None, "actual_end": None, "start_delay_sec": None,
         "status": "pending", "start_status": None, "interruptions": [], "downtime_sec": 0, "ai_failover_count": 0,
         "alerts_critical": 0, "note": "", "final": False, "updated_at": ISO10}
    d.update(kw)
    return d


SANG = sess("friso-sang", slots=[slot("10:00", "12:00", [1, 2, 3, 4, 5, 6, 7])])
TRUA = sess("vns-trua", brand="vinasoy", slots=[slot("13:00", "15:00", [5])])


class TestSlotReport(unittest.TestCase):
    def test_upsert_same_key_by_instant(self):                 # T24
        w = World(T10, [SANG])
        w.report([rec()])
        w.report([rec(planned_start="2026-10-23T10:00:00+07:00", actual_start="2026-10-23T03:01:00Z", status="running",
                      start_status="on_time", start_delay_sec=60)])
        self.assertEqual(len(w.reports.rows), 1)
        key = SR.report_key("MAY01", "friso-sang", T10)
        r = w.reports.rows[key]
        self.assertEqual((r["status"], r["actual_start_ts"], r["planned_start_ts"], r["off_plan"]), ("running", T10 + 60, T10, 0))

    def test_21_slots_accepted_and_bad_one_skipped(self):        # T25
        w = World(T10, [SANG])
        slots = [rec(planned_start="2026-10-23T%02d:00:00.000Z" % h, planned_end="2026-10-23T%02d:30:00.000Z" % h)
                 for h in range(21)] + [rec(live="bad live!"), rec(planned_end=ISO10)]
        out = w.report(slots)
        self.assertEqual((out["saved"], len(out["skipped"]), out["ignored"]), (21, 2, 0))

    def test_unknown_live_saved_off_plan(self):                 # T26
        w = World(T10, [SANG])
        w.report([rec(live="tay-tren-may")])
        self.assertEqual(list(w.reports.rows.values())[0]["off_plan"], 1)

    def test_wrong_machine_token(self):
        w = World(T10, [SANG])
        with self.assertRaises(C.AiLivePermission):
            w.report([rec()], machine="MAY02")


class TestUpsertGuard(unittest.TestCase):
    def test_old_or_unfinal_resend_does_not_overwrite(self):
        from ecentric_workspace.ai_tools.features.ai_live.repositories.slot_report_repository import SR_older
        self.assertTrue(SR_older({"updated_ts": 5, "final": 0}, {"updated_ts": 9, "final": 0}))
        self.assertTrue(SR_older({"updated_ts": 20, "final": 0}, {"updated_ts": 9, "final": 1}))
        self.assertFalse(SR_older({"updated_ts": 20, "final": 1}, {"updated_ts": 9, "final": 1}))
        self.assertFalse(SR_older({"updated_ts": 1, "final": 0}, None))


class TestPlanVsActual(unittest.TestCase):
    def test_chips_and_no_report_after_15_minutes(self):        # T27
        w = World(T10 + 16 * 60, [SANG, TRUA])
        rows = w.actuals()["rows"]
        sang = next(r for r in rows if r["live"] == "friso-sang")
        self.assertTrue(sang["no_report"])
        self.assertEqual(sang["chips"], [{"tone": "idle", "text": "? Không có báo cáo (máy im lặng?)"}])
        trua = next(r for r in rows if r["live"] == "vns-trua")
        self.assertEqual((trua["no_report"], trua["chips"]), (False, []))              # chua toi gio
        w.report([rec(actual_start="2026-10-23T03:04:00Z", status="running", start_status="late", start_delay_sec=240,
                      interruptions=[{"from": "2026-10-23T03:10:00Z", "to": "2026-10-23T03:12:00Z", "reason": "network"}],
                      downtime_sec=120, ai_failover_count=1)])
        out = w.actuals()
        sang = next(r for r in out["rows"] if r["live"] == "friso-sang")
        self.assertEqual([c["text"] for c in sang["chips"]], ["⏰ Trễ 4 phút", "⚡ Gián đoạn 2 phút", "AI dự phòng ×1"])
        self.assertEqual(out["summary"], {"planned": 2, "on_time": 0, "late": 1, "missed": 0, "interrupted": 1, "no_report": 0})

    def test_missed_and_stale_plan(self):
        w = World(T10 + 3600, [SANG])
        w.report([rec(status="missed", note="chưa lên live sau 15 phút"),
                  rec(planned_start="2026-10-23T02:00:00.000Z", planned_end="2026-10-23T03:00:00.000Z", status="on_time",
                      start_status="on_time", actual_start="2026-10-23T02:00:30Z")])
        rows = w.actuals()["rows"]
        self.assertEqual(rows[0]["chips"][-1]["text"], "Kế hoạch cũ / lịch trên máy")      # 09:00 khong co tren ERP
        self.assertTrue(rows[0]["stale_plan"])
        self.assertEqual(rows[1]["chips"], [{"tone": "bad", "text": "✗ Lỡ"}])
        self.assertEqual(w.actuals()["summary"]["missed"], 1)

    def test_bad_day(self):
        with self.assertRaises(C.AiLiveError):
            World(T10).actuals("23/10")


class TestWallboard(unittest.TestCase):
    def test_counters_order_lost_machine_cost_ai(self):
        w = World(T10 + 30 * 60, [SANG, TRUA])
        w.costs.day = {"friso": 1.2}
        on_air = [{"live": "friso-sang", "brand": "friso", "mode": "camera", "since": "2026-10-23T03:00:05Z"}]
        w.push([live(live="friso-sang", alerts=[{"code": "esync_down", "level": "critical", "text": "Mất eSync",
                                                 "since": (T10 + 26 * 60) * 1000}],
                     ai={"mode": "backup", "label": "MiniMax"}, schedule=[]),
                live(live="L2", brand="wilmar", schedule=[], metrics={"fps": 18, "outputActive": True})],
               on_air=on_air)
        d = w.wall()
        self.assertEqual(d["counters"], {"on_air": 2, "crit": 1, "warn": 1, "lost": 0, "missed_today": 0})
        c = d["cards"][0]
        self.assertEqual((c["live"], c["level"], c["problem"]["text"], c["title"]), ("friso-sang", "crit", "Mất eSync", "FRISO-SANG"))
        self.assertEqual((c["mode"], c["on_air_since_ts"], c["ai"]["text"]), ("camera", T10 + 5, "AI: dự phòng"))
        self.assertEqual(c["cost"]["text"], "$1.20 / $5 (24%)")
        self.assertEqual(d["cards"][1]["level"], "warn")
        self.assertEqual([x["live"] for x in d["waiting"]], ["vns-trua"])
        w.at(4)                                                     # may im lang 4 phut
        w.watch()
        d = w.wall()
        self.assertEqual(d["counters"]["lost"], 1)
        self.assertEqual(d["lost_machines"][0]["machine"], "MAY01")
        self.assertIn("friso – FRISO-SANG", d["lost_machines"][0]["lives"])
        self.assertTrue(d["lost_machines"][0]["incident"]["name"])
        self.assertTrue(all(x["level"] == "lost" for x in d["cards"]))
        self.assertEqual(len(w.wall(brand="vinasoy")["cards"]), 0)

    def test_missed_today_counts_no_report_only_for_reporting_apps(self):
        w = World(T10 + 20 * 60, [SANG])
        w.push([live(live="L9", state="idle", schedule=[])], app={"version": "1.0.20"})
        self.assertEqual(w.wall()["counters"]["missed_today"], 0)     # app cu chua gui push_slot_report -> khong tinh
        w.push([live(live="L9", state="idle", schedule=[])], app={"version": "1.0.21"})
        self.assertEqual(w.wall()["counters"]["missed_today"], 1)
        self.assertEqual(w.wall(brand="vinasoy")["counters"]["missed_today"], 0)      # theo bo loc

    def test_wall_command_and_status(self):
        w = World(T10, [SANG])
        svc = QueueCommandService(w.sess, w.cmds, w.clock)
        out = svc.execute_wall("truc@ec", VIEW, "MAY01", "tay-tren-may", "pause_ai", None, machines=w.machines)
        self.assertEqual(out["status"], C.CMD_QUEUED)
        self.assertEqual(w.cmds.rows[out["id"]]["live"], "tay-tren-may")
        for bad in (("MAY09", "L1", "pause_ai", None), ("MAY01", "L1", "start_race", None), ("MAY01", "L1", "play_faq", {})):
            with self.assertRaises(C.AiLiveError):
                svc.execute_wall("truc@ec", VIEW, *bad, machines=w.machines)
        st = CommandStatusService(w.cmds).execute(VIEW, '["%s"]' % out["id"])
        self.assertEqual(st["commands"][0]["status"], C.CMD_QUEUED)
        w.push([live(live="tay-tren-may", schedule=[])])
        self.assertEqual(w.wall()["cards"][0]["commands"][0]["action"], "pause_ai")

    def test_extra_kept_on_minimal_beat(self):
        prev = R.sanitize_extra({"faq": [{"id": 1, "title": "Giá"}], "ai": {"mode": "main", "label": "Claude"}}, {})
        cur = R.sanitize_extra({"ai": {"mode": "backup"}}, prev)
        self.assertEqual((cur["faq"], cur["ai"]["mode"]), ([{"id": "1", "title": "Giá"}], "backup"))


if __name__ == "__main__":
    unittest.main()
