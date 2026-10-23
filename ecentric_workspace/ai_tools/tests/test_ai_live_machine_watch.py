# Copyright (c) 2026, eCentric and contributors
"""W17 (fix10f) - may AI Live im lang: luu nhip tim ca may, bao KHAN khi im lang > 3 phut luc dang co live,
khong bao khi tat app dung cach / khong co live, nhac lai theo gio, bao lien lac lai, kenh theo nhom brand.
Chay ngoai Frappe."""
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.alert_test_service import AlertTestService
from ecentric_workspace.ai_tools.features.ai_live.application.monitor_tick_service import MonitorTickService
from ecentric_workspace.ai_tools.features.ai_live.application.push_heartbeat_service import PushHeartbeatService
from ecentric_workspace.ai_tools.features.ai_live.application.watch_machines_service import WatchMachinesService
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import (ADMIN, Clock, FakeAlerts, FakeHealth, FakeIncidents,
                                                                    FakeSamples, FakeSettings, FakeThumbs, live, vn_ts)

T0 = vn_ts(2026, 10, 19, 20, 0)      # thu Hai 20:00 gio VN
NIGHT = vn_ts(2026, 10, 20, 2, 0)    # thu Ba 02:00
BOOT = vn_ts(2026, 10, 19, 8, 0)
STARTED = vn_ts(2026, 10, 19, 8, 1)


class Machines:
    """Giu nhip tim + moc watch_* nhu EC AI Live Machine."""

    def __init__(self):
        self.rows = {"MAY01": {"machine_code": "MAY01", "label": "Máy 1", "enabled": 1, "user": "u1",
                               "brands": "friso\nwilmar"}}

    def by_user(self, user):
        return next((dict(m) for m in self.rows.values() if m["user"] == user), None)

    def save_heartbeat(self, code, vals):
        self.rows[code].update(vals)

    set_watch = save_heartbeat

    def heartbeats(self):
        return [dict(m) for m in self.rows.values() if m.get("enabled") and m.get("hb_last_seen_ts")]


class Sessions:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def list(self, filters=None):
        return [s for s in self.rows if not filters or all(s.get(k) == v for k, v in filters.items())]


class Sender:
    """Ghi lai cfg tung kenh de kiem chon kenh; tra OFF khi kenh tat giong ban that."""

    def __init__(self):
        self.sent = []

    def send_teams(self, cfg, level, title, text, link):
        if not (cfg.get("teams_enabled") and cfg.get("teams_webhook_url")):
            return False, "OFF"
        self.sent.append(("teams", cfg["group"], cfg["teams_webhook_url"], level, title, text))
        return True, "200"

    def send_zalo(self, cfg, title, text, link):
        if not (cfg.get("zalo_enabled") and cfg.get("zalo_bot_token") and cfg.get("zalo_chat_id")):
            return False, "OFF"
        self.sent.append(("zalo", cfg["group"], cfg["zalo_chat_id"], None, title, text))
        return True, "200"


def session(**kw):
    d = {"id": "friso-toi", "title": "Phiên tối", "brand": "friso", "machine": "MAY01", "enabled": 1,
         "slots": [{"days": [1, 2, 3, 4, 5, 6, 7], "date": None, "start": "19:00", "end": "23:00"}]}
    d.update(kw)
    return d


class World:
    def __init__(self, t0, sessions=(), **settings):
        self.clock = Clock(t0)
        self.machines, self.sessions = Machines(), Sessions(sessions)
        self.health, self.samples, self.thumbs, self.alerts = FakeHealth(), FakeSamples(), FakeThumbs(), FakeAlerts()
        self.settings, self.sender, self.incidents = FakeSettings(**settings), Sender(), FakeIncidents()

    def push(self, lives=None, **top):
        p = dict({"machine": "MAY01", "at": self.clock.t, "app": {"version": "1.0.20", "uptimeMs": 1000},
                  "state": "running", "boot_at": BOOT, "app_started_at": STARTED}, **top)
        p["lives"] = [live()] if lives is None else lives
        return PushHeartbeatService(self.machines, self.health, self.samples, self.thumbs, self.clock).execute("u1", p)

    def watch(self):
        svc = WatchMachinesService(self.machines, self.sessions, self.health, self.alerts, self.settings, self.sender,
                                   self.clock, "https://x/m", self.incidents)
        return sum(svc.check(m) for m in svc.targets())

    def tick(self):
        svc = MonitorTickService(self.health, self.samples, self.alerts, self.settings, self.sender, self.clock,
                                 "https://x/m", self.machines, self.incidents)
        return sum(svc.check(r) for r in svc.targets())

    def at(self, minutes):
        self.clock.t += minutes * 60
        return self

    @property
    def m(self):
        return self.machines.rows["MAY01"]

    def last(self):
        return self.alerts.rows[-1]


class TestHeartbeatSaved(unittest.TestCase):
    def test_machine_fields(self):
        w = World(T0)
        idle = live(live="L2", brand="wilmar", state="idle",
                    alerts=[{"code": "listener_down", "level": "warn", "text": "Mất bình luận"}])
        w.push([live(), idle])
        m = w.m
        self.assertEqual((m["hb_last_seen_ts"], m["hb_state"], m["hb_version"]), (T0, "running", "1.0.20"))
        self.assertEqual((m["hb_boot_ts"], m["hb_started_ts"], m["hb_on_air"]), (BOOT, STARTED, 1))
        self.assertEqual(m["hb_lives"], [{"live": "L1", "brand": "friso"}])
        self.assertEqual(m["hb_alerts"], ["L2: Mất bình luận (vàng)"])

    def test_old_app_and_empty_lives(self):
        w = World(T0)
        w.push([], state=None, boot_at=None, app_started_at=None, app={"version": "1.0.12"})
        self.assertEqual((w.m["hb_state"], w.m["hb_boot_ts"], w.m["hb_on_air"], w.m["hb_lives"]), ("running", 0, 0, []))
        w.push([live(state="idle")], on_air=["L1"], boot_at="2026-10-19T01:00:00Z")
        self.assertEqual(w.m["hb_lives"], [{"live": "L1", "brand": "friso"}])
        self.assertEqual(w.m["hb_boot_ts"], BOOT)


class TestLost(unittest.TestCase):
    def test_khan_after_3_minutes_not_before(self):
        w = World(T0)
        w.push()
        self.assertEqual((w.at(2.5).watch(), w.tick()), (0, 0))   # 2.5 phut: chua bao, live cung khong bao le
        self.assertEqual(w.at(1).watch(), 1)
        a = w.last()
        self.assertEqual((a["code"], a["level"], a["health_key"]), (C.WatchCode.OFFLINE, C.Level.CRIT, "machine:MAY01"))
        self.assertEqual(a["text"], "Máy MAY01 (Máy 1) mất liên lạc từ 20:00 (mất điện / mất mạng / treo). "
                                    "Đang có live: friso – L1.")
        self.assertEqual([(s[0], s[4]) for s in w.sender.sent],
                         [("teams", "[KHẨN] AI Live · Máy MAY01 (Máy 1)"), ("zalo", "[KHẨN] AI Live · Máy MAY01 (Máy 1)")])
        self.assertEqual(w.tick(), 0)                              # 1 tin theo may, khong them tin tung live
        self.assertEqual(w.m["watch_lost_ts"], T0)

    def test_stopping_or_no_live_sends_nothing(self):
        w = World(T0, sessions=[session()])
        w.push([live(state="stopped")], state="stopping")
        self.assertEqual((w.at(30).watch(), w.tick()), (0, 0))     # tat app dung cach: ke ca trong gio phien ERP
        w2 = World(T0)
        w2.push([live(state="idle", schedule=[])])
        self.assertEqual((w2.at(30).watch(), w2.tick()), (0, 0))   # khong co live nao
        w3 = World(T0)
        w3.push([])
        self.assertEqual(w3.at(30).watch(), 0)

    def test_erp_session_window_counts_as_live(self):
        w = World(T0, sessions=[session(), session(id="wil-sang", brand="wilmar", title="Sáng", slots=[
            {"days": [1], "date": None, "start": "08:00", "end": "10:00"}])])
        w.push([live(state="idle", schedule=[])])
        self.assertEqual(w.at(4).watch(), 1)
        self.assertIn("Đang có live: friso – Phiên tối.", w.last()["text"])
        self.assertEqual(w.last()["brand"], "friso")

    def test_disabled_settings(self):
        w = World(T0, enabled=0)
        w.push()
        self.assertEqual(w.at(10).watch(), 0)


class TestRepeat(unittest.TestCase):
    def test_day_every_5_minutes(self):
        w = World(T0)
        w.push()
        self.assertEqual(w.at(3.5).watch(), 1)
        self.assertEqual(sum(w.at(1).watch() for _ in range(4)), 0)
        self.assertEqual(w.at(1).watch(), 1)
        self.assertIn("Đã 8 phút chưa liên lạc lại.", w.last()["text"])
        self.assertIn("mất liên lạc từ 20:00", w.last()["text"])

    def test_night_every_15_minutes(self):
        w = World(NIGHT, incident_escalate_min=60)          # fix10h: leo thang (10 phut) test rieng o test_ai_live_incident
        w.push([live(schedule=[])])
        self.assertEqual(w.at(3.5).watch(), 1)
        self.assertEqual(sum(w.at(1).watch() for _ in range(14)), 0)
        self.assertEqual(w.at(1).watch(), 1)

    def test_configurable(self):
        w = World(T0, machine_offline_min=1, machine_repeat_min=2)
        w.push()
        self.assertEqual(w.at(1.5).watch(), 1)
        self.assertEqual((w.at(1).watch(), w.at(1).watch()), (0, 1))
        cfg = {"night_start": "22:00", "night_end": "06:00", "night_repeat_min": 30, "machine_repeat_min": 5}
        self.assertEqual((W.repeat_minutes(vn_ts(2026, 10, 19, 23, 0), cfg), W.repeat_minutes(T0, cfg)), (30, 5))
        self.assertEqual(W.repeat_minutes(NIGHT, {"night_start": "xx"}), C.NIGHT_REPEAT_MIN)


class TestBack(unittest.TestCase):
    def lost_world(self):
        w = World(T0)
        w.push()
        w.at(4).watch()
        return w.at(6)

    def test_back_after_n_minutes(self):
        w = self.lost_world()
        w.push()                                                   # mat mang 10 phut, may khong khoi dong lai
        self.assertEqual(w.at(0.5).watch(), 1)
        a = w.last()
        self.assertEqual((a["code"], a["level"]), (C.WatchCode.BACK, C.Level.INFO))
        self.assertEqual(a["text"], "Máy MAY01 (Máy 1) đã liên lạc lại sau 10 phút. "
                                    "Máy không khởi động lại (mất mạng / ERP không nhận được nhịp tim).")
        self.assertTrue(w.sender.sent[-1][4].startswith("[XANH]"))
        self.assertEqual((w.m["watch_lost_ts"], w.m["watch_back_ts"]), (0, 0))
        self.assertEqual(w.at(1).watch(), 0)

    def test_reboot_is_power_loss(self):
        w = self.lost_world()
        w.push(boot_at=w.clock.t - 90, app_started_at=w.clock.t - 30)
        w.at(1).watch()
        self.assertEqual(w.last()["text"], "Máy MAY01 (Máy 1) đã liên lạc lại sau 10 phút. "
                                           "Máy vừa khởi động lại (mất điện / reset).")

    def test_app_restart_after_crash(self):
        w = self.lost_world()
        w.push(app_started_at=w.clock.t - 20, resume={"resumed_at": w.clock.t, "from_crash": True})
        w.at(1).watch()
        self.assertIn("App eC Live vừa mở lại sau lỗi", w.last()["text"])

    def test_back_even_without_live(self):
        w = self.lost_world()
        w.push([], state="stopping")
        self.assertEqual(w.at(1).watch(), 1)
        self.assertEqual(w.last()["code"], C.WatchCode.BACK)


class TestLiveVsMachine(unittest.TestCase):
    def test_single_live_gone_while_machine_alive_still_alerts_live(self):
        w = World(T0)
        w.push()
        for _ in range(3):
            w.at(1).push([])                                       # app van gui nhip tim, rieng L1 mat
        self.assertEqual((w.tick(), w.watch()), (1, 0))
        self.assertEqual(w.alerts.rows[-1]["code"], "offline")


class TestChannels(unittest.TestCase):
    CH = [{"enabled": 1, "group_name": "Friso", "brands": "friso", "teams_enabled": 1, "teams_webhook_url": "https://hookA",
           "zalo_enabled": 1, "zalo_chat_id": "gF", "zalo_bot_token": ""},
          {"enabled": 1, "group_name": "Wilmar", "brands": "wilmar", "teams_enabled": 0, "zalo_enabled": 1, "zalo_chat_id": "gW"},
          {"enabled": 1, "group_name": "Trực", "brands": "", "teams_enabled": 1, "teams_webhook_url": "https://hook"},
          {"enabled": 0, "group_name": "Tắt", "brands": "friso", "zalo_enabled": 1, "zalo_chat_id": "gX"}]

    def test_routing_by_brand(self):
        w = World(T0, channels=self.CH)
        w.push()
        w.at(4).watch()
        got = sorted((s[0], s[1], s[2]) for s in w.sender.sent)
        self.assertEqual(got, [("teams", "", "https://hook"), ("teams", "Friso", "https://hookA"),
                               ("zalo", "", "g1"), ("zalo", "Friso", "gF")])   # nhom Truc trung webhook chung -> 1 lan
        a = w.last()
        self.assertEqual((a["teams_result"], a["zalo_result"]), ("200,Friso:200", "200,Friso:200"))
        blob = repr(w.alerts.rows)
        self.assertNotIn("1:abc", blob)
        self.assertNotIn("hookA", blob)

    def test_group_without_default(self):
        cfg = dict(FakeSettings(teams_enabled=0, zalo_enabled=0, channels=self.CH).get(with_secrets=True))
        chans = A.channels_for(cfg, ["wilmar"])
        self.assertEqual([c["group"] for c in chans], ["", "Wilmar", "Trực"])
        self.assertEqual(chans[1]["zalo_bot_token"], "1:abc")                 # dung token bot chung

    def test_alert_test_sends_every_group(self):
        s = Sender()
        r = AlertTestService(FakeSettings(channels=self.CH), s).execute(ADMIN)
        self.assertTrue(r["teams"]["ok"] and r["zalo"]["ok"])
        self.assertEqual([g["group"] for g in r["groups"]], ["Friso", "Wilmar", "Trực"])
        self.assertEqual(r["groups"][1], {"group": "Wilmar", "teams": "OFF", "zalo": "200"})


if __name__ == "__main__":
    unittest.main()
