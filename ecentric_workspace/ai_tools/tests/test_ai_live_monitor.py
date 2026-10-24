# Copyright (c) 2026, eCentric and contributors
"""Giam sat AI Live (fix10c): tin hieu may phat, danh gia muc, quet moi phut, tuong Giam sat - chay ngoai Frappe."""
import base64
import unittest
from datetime import datetime, timedelta, timezone

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.alert_test_service import AlertTestService
from ecentric_workspace.ai_tools.features.ai_live.application.monitor_detail_service import MonitorDetailService
from ecentric_workspace.ai_tools.features.ai_live.application.monitor_thumb_service import MonitorThumbService
from ecentric_workspace.ai_tools.features.ai_live.application.monitor_tick_service import MonitorTickService
from ecentric_workspace.ai_tools.features.ai_live.application.monitor_wall_service import MonitorWallService
from ecentric_workspace.ai_tools.features.ai_live.application.push_heartbeat_service import (PushHeartbeatService,
                                                                                             decode_thumb)
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.infrastructure import alert_channels

JPG = b"\xff\xd8\xff\xe0" + b"x" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 40
VN = timezone(timedelta(hours=7))
VIEW, ADMIN, NOBODY = ["EC AI Content"], ["EC AI Video Admin"], ["Employee"]


def vn_ts(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=VN).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeMachines:
    def by_user(self, user):
        return {"u1": {"machine_code": "MAY01", "enabled": 1, "user": "u1", "brands": "friso\nwilmar"},
                "u2": {"machine_code": "MAY02", "enabled": 0, "user": "u2", "brands": "friso"}}.get(user)

    def save_heartbeat(self, code, vals):      # fix10f: nhip tim ca may (test may im lang o test_ai_live_machine_watch)
        self.__dict__.setdefault("hb", {}).setdefault(code, {}).update(vals)

    def heartbeats(self):
        return []


class FakeHealth:
    def __init__(self):
        self.rows = {}
        self.flags = []

    def get(self, key):
        r = self.rows.get(key)
        return dict(r) if r else None

    def all(self):
        return [dict(r) for _, r in sorted(self.rows.items())]

    def upsert(self, key, row):
        cur = self.rows.setdefault(key, {"key": key, "offline_alerted": 0, "obs_thumb_ts": 0, "phone_thumb_ts": 0})
        cur.update(row)

    def set_flag(self, key, v):
        self.rows[key]["offline_alerted"] = 1 if v else 0
        self.flags.append((key, bool(v)))


class FakeSamples:
    def __init__(self):
        self.rows, self.purged = [], None

    def last_ts(self, key):
        return max([r["ts"] for r in self.rows if r["key"] == key] or [0])

    def insert(self, key, ts, level, metrics):
        self.rows.append({"key": key, "ts": ts, "level": level, "fps": metrics.get("fps")})

    def since(self, key, ts):
        return [r for r in self.rows if r["key"] == key and r["ts"] >= ts]

    def purge(self, before):
        self.purged = before


class FakeThumbs:
    def __init__(self):
        self.files = {}

    def save(self, key, kind, data, ext):
        self.files[(key, kind)] = (data, "image/jpeg" if ext == "jpg" else "image/png")

    def read(self, key, kind):
        return self.files.get((key, kind))


class FakeAlerts:
    def __init__(self):
        self.rows, self.purged = [], None

    def last_sent(self, akey):
        r = [x for x in self.rows if x["alert_key"] == akey]
        return {"ts": r[-1]["sent_ts"], "level": r[-1]["level"]} if r else None

    def insert(self, row):
        self.rows.append(row)

    def for_key(self, key, since):
        return [{"ts": r["sent_ts"], "level": r["level"], "code": r["code"], "text": r["text"]}
                for r in reversed(self.rows) if r["health_key"] == key and r["sent_ts"] >= since]

    def latest_by_key(self, since):
        out = {}
        for r in self.rows:
            if r["sent_ts"] >= since:
                out[r["health_key"]] = {"ts": r["sent_ts"], "level": r["level"], "text": r["text"]}
        return out

    def purge(self, before):
        self.purged = before


class FakeSettings:
    def __init__(self, **kw):
        self.d = {"enabled": 1, "teams_enabled": 1, "teams_format": "workflows", "zalo_enabled": 1, "zalo_chat_id": "g1",
                  "zalo_api_base": C.ZALO_API_BASE, "zalo_send_path": C.ZALO_SEND_PATH, "dead_man_min": 2,
                  "dedupe_min": 10, "escalate_min": 5, "teams_webhook_url": "https://hook", "zalo_bot_token": "1:abc"}
        self.d.update(kw)

    def get(self, with_secrets=False):
        d = dict(self.d)
        if not with_secrets:
            d.pop("teams_webhook_url", None)
            d.pop("zalo_bot_token", None)
        return d


class FakeIncidents:
    """fix10h: EC AI Live Incident trong bo nho."""

    def __init__(self):
        self.rows, self.purged, self.n = {}, None, 0

    def insert(self, row):
        self.n += 1
        name = "INC%03d" % self.n
        d = {"name": name, "sent_count": 0, "acked_by": "", "ack_note": "", "resolve_text": ""}
        for k in ("opened_ts", "first_sent_ts", "last_sent_ts", "acked_ts", "escalated_ts", "resolved_ts", "missing_since_ts"):
            d[k] = 0.0
        d.update(row)
        self.rows[name] = d
        return name

    def update(self, name, vals):
        self.rows[name].update(vals)

    def get(self, name):
        r = self.rows.get(name)
        return dict(r) if r else None

    def _open(self):
        return [dict(r) for r in self.rows.values() if r["status"] in (C.IncStatus.OPEN, C.IncStatus.ACKED)]

    def open_by_key(self, key):
        r = [x for x in self._open() if x["incident_key"] == key]
        return r[-1] if r else None

    def open_all(self, kind=None):
        return [x for x in self._open() if not kind or x["kind"] == kind]

    def by_status(self, status, since_ts, limit=200):
        return [dict(r) for r in self.rows.values() if r["status"] == status
                and (status != C.IncStatus.DONE or r["resolved_ts"] >= since_ts)][:limit]

    def counts(self, since_ts):
        out = {}
        for r in self.rows.values():
            if r["status"] != C.IncStatus.DONE or r["resolved_ts"] >= since_ts:
                out[r["status"]] = out.get(r["status"], 0) + 1
        return out

    def purge(self, before):
        self.purged = before


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_teams(self, cfg, level, title, text, link):
        self.sent.append(("teams", level, title, text))
        return True, "200"

    def send_zalo(self, cfg, title, text, link):
        self.sent.append(("zalo", None, title, text))
        return True, "200"


def b64(data):
    return base64.b64encode(data).decode()


class World:
    def __init__(self, t0):
        self.clock = Clock(t0)
        self.health, self.samples, self.thumbs, self.alerts = FakeHealth(), FakeSamples(), FakeThumbs(), FakeAlerts()
        self.settings, self.sender, self.incidents = FakeSettings(), FakeSender(), FakeIncidents()

    def push(self, payload, user="u1"):
        return PushHeartbeatService(FakeMachines(), self.health, self.samples, self.thumbs, self.clock).execute(user, payload)

    def tick(self):
        svc = MonitorTickService(self.health, self.samples, self.alerts, self.settings, self.sender, self.clock, "https://x/m",
                                 FakeMachines(), self.incidents)
        return sum(svc.check(r) for r in svc.targets())

    def wall(self, roles=VIEW, **kw):
        return MonitorWallService(self.health, self.alerts, self.settings, self.clock).execute(roles, **kw)


T0 = vn_ts(2026, 10, 19, 20, 0)  # thu Hai 20:00 gio VN


def live(**kw):
    d = {"live": "L1", "brand": "friso", "state": "live",
         "metrics": {"activeFps": 30, "dropped_pct": 0.1, "gpuPct": 40, "kbps": 6000, "outputActive": True},
         "schedule": [{"days": [1, 2, 3, 4, 5], "start": "19:00", "end": "22:00"}]}
    d.update(kw)
    return d


class TestThumb(unittest.TestCase):
    def test_decode(self):
        self.assertEqual(decode_thumb(b64(JPG)), (JPG, "jpg"))
        self.assertEqual(decode_thumb("data:image/png;base64," + b64(PNG)), (PNG, "png"))
        for bad in ("@@@", b64(b"GIF89a....")):
            with self.assertRaises(C.AiLiveError):
                decode_thumb(bad)
        with self.assertRaises(C.AiLiveError):
            decode_thumb("A" * (C.MAX_THUMB_BYTES * 2))


class TestHeartbeat(unittest.TestCase):
    def test_saves_normalizes_and_samples_once_per_minute(self):
        w = World(T0)
        r = w.push({"machine": "MAY01", "lives": [live(thumb_b64=b64(JPG), phone_thumb_b64=b64(PNG))]})
        self.assertEqual(r["saved"], ["L1"])
        row = w.health.get("MAY01__L1")
        self.assertEqual(row["metrics"]["fps"], 30.0)
        self.assertEqual(row["metrics"]["gpu"], 40.0)
        self.assertTrue(row["metrics"]["streaming"])
        self.assertEqual(row["obs_thumb_ts"], T0)
        self.assertIn(("MAY01__L1", "phone"), w.thumbs.files)
        w.clock.t += 30
        w.push({"machine": "MAY01", "lives": [live()]})
        self.assertEqual(len(w.samples.rows), 1)
        w.clock.t += 31
        w.push({"machine": "MAY01", "lives": [live()]})
        self.assertEqual(len(w.samples.rows), 2)

    def test_skips_bad_lives_and_keeps_good(self):
        w = World(T0)
        r = w.push({"machine": "MAY01", "lives": [live(live="bad id!"), live(live="L2", brand="vinasoy"),
                                                  live(live="L3", thumb_b64="xx")]})
        self.assertEqual(r["saved"], [])
        self.assertEqual([s["live"] for s in r["skipped"]], ["bad id!", "L2", "L3"])
        self.assertIsNotNone(w.health.get("MAY01__L3"))  # anh hong khong lam mat tin hieu

    def test_auth(self):
        w = World(T0)
        with self.assertRaises(C.AiLivePermission):
            w.push({"machine": "MAY01", "lives": []}, user="u2")
        with self.assertRaises(C.AiLivePermission):
            w.push({"machine": "MAY09", "lives": []})
        with self.assertRaises(C.AiLiveError):
            w.push({"machine": "MAY01", "lives": "x"})
        r = w.push({"machine": "MAY01", "lives": [live(live="L%d" % i) for i in range(60)]})   # 1.0.21: toi 50, thua thi cat
        self.assertEqual(len(r["saved"]), C.MAX_HB_LIVES)

    def test_server_reasons_and_since_kept(self):
        w = World(T0)
        m = {"activeFps": 18, "outputActive": False}
        w.push({"machine": "MAY01", "lives": [live(metrics=m, alerts=[{"code": "listener_down", "level": "warn", "text": "Mất comment"}])]})
        codes = {a["code"]: a for a in w.health.get("MAY01__L1")["alerts"]}
        self.assertEqual(set(codes), {"listener_down", "not_streaming", "low_fps"})
        self.assertEqual(codes["not_streaming"]["level"], C.Level.CRIT)
        w.clock.t += 120
        w.push({"machine": "MAY01", "lives": [live(metrics=m, alerts=[{"code": "listener_down", "level": "warn"}])]})
        again = {a["code"]: a for a in w.health.get("MAY01__L1")["alerts"]}
        self.assertEqual(again["listener_down"]["since"], T0)
        self.assertEqual(again["low_fps"]["since"], T0)

    def test_top_level_thumb_single_or_map(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live()], "thumb_b64": b64(JPG)})
        self.assertIn(("MAY01__L1", "obs"), w.thumbs.files)
        w.push({"machine": "MAY01", "lives": [live(live="A"), live(live="B")], "thumb_b64": {"B": b64(PNG)}})
        self.assertIn(("MAY01__B", "obs"), w.thumbs.files)
        self.assertNotIn(("MAY01__A", "obs"), w.thumbs.files)


class TestRules(unittest.TestCase):
    cfg = {"dead_man_min": 2, "escalate_min": 5}

    def test_schedule(self):
        slots = R.sanitize_schedule([{"days": [1], "start": "19:00", "end": "22:00"}, {"days": [7], "start": "22:00", "end": "02:00"},
                                     {"start": "25:00", "end": "26:00"}, "x"])
        self.assertEqual(len(slots), 2)
        self.assertTrue(R.in_schedule(slots, vn_ts(2026, 10, 19, 21, 59)))
        self.assertFalse(R.in_schedule(slots, vn_ts(2026, 10, 19, 22, 0)))
        self.assertFalse(R.in_schedule(slots, vn_ts(2026, 10, 20, 20, 0)))  # thu Ba
        self.assertTrue(R.in_schedule(slots, vn_ts(2026, 10, 19, 1, 30)))   # dem Chu nhat -> sang thu Hai
        self.assertTrue(R.in_schedule(slots, vn_ts(2026, 10, 18, 23, 0)))

    def test_offline_vs_idle(self):
        row = {"state": "live", "last_seen_ts": T0 - 200, "schedule": []}
        self.assertEqual(R.evaluate(row, T0, self.cfg)["level"], C.Level.OFF)
        row = {"state": "stopped", "last_seen_ts": T0 - 200, "schedule": []}
        self.assertEqual(R.evaluate(row, T0, self.cfg)["level"], C.Level.IDLE)
        row = {"state": "stopped", "last_seen_ts": T0 - 200,
               "schedule": [{"days": [1], "start": "19:00", "end": "22:00"}]}
        self.assertEqual(R.evaluate(row, T0, self.cfg)["level"], C.Level.OFF)  # may chet truoc gio len live
        row = {"state": "live", "last_seen_ts": T0 - 90, "schedule": []}
        ev = R.evaluate(row, T0, self.cfg)
        self.assertEqual((ev["level"], ev["reasons"][0]["code"]), (C.Level.WARN, "stale"))

    def test_escalation_and_dedupe(self):
        row = {"state": "live", "last_seen_ts": T0, "alerts": [{"code": "gpu_high", "level": "warn", "text": "x", "since": T0 - 301}]}
        ev = R.evaluate(row, T0, self.cfg)
        self.assertEqual(ev["level"], C.Level.CRIT)
        self.assertTrue(ev["reasons"][0]["escalated"])
        self.assertTrue(R.should_send(None, "warn", T0, 10))
        self.assertFalse(R.should_send({"ts": T0 - 60, "level": "critical"}, "critical", T0, 10))
        self.assertTrue(R.should_send({"ts": T0 - 60, "level": "warn"}, "critical", T0, 10))
        self.assertTrue(R.should_send({"ts": T0 - 600, "level": "critical"}, "critical", T0, 10))

    def test_metrics_aliases_and_bounds(self):
        m = R.normalize_metrics({"fps": "29.97", "gpu": 140, "last_comment_at": (T0 - 65) * 1000, "clip": "x" * 200}, T0)
        self.assertEqual(m["fps"], 29.97)
        self.assertNotIn("gpu", m)
        self.assertEqual(m["comment_age_s"], 65)
        self.assertEqual(len(m["clip"]), 80)


class TestTick(unittest.TestCase):
    def test_dead_man_once_then_back(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live()]})
        self.assertEqual(w.tick(), 0)
        w.clock.t += 150  # mat dien
        self.assertEqual(w.tick(), 1)
        self.assertEqual(w.alerts.rows[0]["code"], "offline")
        self.assertEqual(w.alerts.rows[0]["level"], C.Level.CRIT)
        self.assertEqual([s[0] for s in w.sender.sent], ["teams", "zalo"])
        self.assertEqual(w.health.get("MAY01__L1")["offline_alerted"], 1)
        w.clock.t += 60
        self.assertEqual(w.tick(), 0)  # chong lap 10 phut
        w.clock.t += 600
        self.assertEqual(w.tick(), 1)  # qua 10 phut van mat -> bao lai
        w.push({"machine": "MAY01", "lives": [live()]})
        self.assertEqual(w.tick(), 1)
        self.assertEqual(w.alerts.rows[-1]["code"], "back")
        self.assertEqual(w.health.get("MAY01__L1")["offline_alerted"], 0)

    def test_escalates_warn_and_forwards_server_critical(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live(metrics={"gpuPct": 97, "outputActive": True})]})
        self.assertEqual(w.tick(), 0)
        for _ in range(6):
            w.clock.t += 60
            w.push({"machine": "MAY01", "lives": [live(metrics={"gpuPct": 97, "outputActive": True})]})
        self.assertEqual(w.tick(), 1)
        self.assertEqual(w.alerts.rows[0]["code"], "gpu_high.esc")
        w.push({"machine": "MAY01", "lives": [live(metrics={"outputActive": False})]})
        w.tick()
        self.assertIn("not_streaming", [r["code"] for r in w.alerts.rows])

    def test_disabled_and_idle_send_nothing(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live(state="stopped", schedule=[])]})
        w.clock.t += 3600
        self.assertEqual(w.tick(), 0)
        w2 = World(T0)
        w2.settings = FakeSettings(enabled=0)
        w2.push({"machine": "MAY01", "lives": [live()]})
        w2.clock.t += 600
        self.assertEqual(w2.tick(), 0)

    def test_purge(self):
        w = World(T0)
        svc = MonitorTickService(w.health, w.samples, w.alerts, w.settings, w.sender, w.clock, machines=FakeMachines(),
                                 incidents=w.incidents)
        svc.purge()
        self.assertEqual(w.samples.purged, T0 - 86400)
        self.assertEqual(w.alerts.purged, T0 - 14 * 86400)


class TestWall(unittest.TestCase):
    def test_wall_counts_filters_order(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live(live="A"), live(live="B", brand="wilmar", metrics={"gpuPct": 97}),
                                              live(live="C", state="stopped", schedule=[])]})
        w.clock.t += 10
        out = w.wall()
        self.assertEqual([t["live"] for t in out["tiles"]], ["B", "A", "C"])
        self.assertEqual(out["counts"], {"total": 3, "critical": 0, "warn": 1, "ok": 1, "idle": 1})
        self.assertEqual(out["brands"], ["friso", "wilmar"])
        self.assertEqual([t["live"] for t in w.wall(level="problem")["tiles"]], ["B"])
        self.assertEqual([t["live"] for t in w.wall(brand="friso")["tiles"]], ["A", "C"])
        w.clock.t += 8 * 86400
        self.assertEqual(w.wall()["counts"]["total"], 2)  # C ngoai gio > 7 ngay: an
        with self.assertRaises(C.AiLivePermission):
            w.wall(roles=NOBODY)

    def test_detail_and_thumb(self):
        w = World(T0)
        w.push({"machine": "MAY01", "lives": [live(thumb_b64=b64(JPG))]})
        d = MonitorDetailService(w.health, w.samples, w.alerts, w.settings, w.clock).execute(VIEW, "MAY01__L1")
        self.assertEqual(len(d["samples"]), 1)
        self.assertEqual(d["level"], C.Level.OK)
        with self.assertRaises(C.AiLiveError):
            MonitorDetailService(w.health, w.samples, w.alerts, w.settings, w.clock).execute(VIEW, "MAY01__X")
        t = MonitorThumbService(w.thumbs)
        self.assertTrue(t.execute(VIEW, "MAY01__L1", "obs")["data_uri"].startswith("data:image/jpeg;base64,"))
        for args in ((VIEW, "MAY01__L1", "phone"), (VIEW, "../etc", "obs"), (VIEW, "MAY01__L1", "x")):
            with self.assertRaises(C.AiLiveError):
                t.execute(*args)
        with self.assertRaises(C.AiLivePermission):
            t.execute(NOBODY, "MAY01__L1", "obs")


class TestChannels(unittest.TestCase):
    def test_alert_test_service(self):
        s = FakeSender()
        r = AlertTestService(FakeSettings(), s).execute(ADMIN)
        self.assertTrue(r["teams"]["ok"] and r["zalo"]["ok"])
        with self.assertRaises(C.AiLivePermission):
            AlertTestService(FakeSettings(), s).execute(VIEW)
        with self.assertRaises(C.AiLiveError):
            AlertTestService(FakeSettings(teams_enabled=0, zalo_enabled=0), s).execute(ADMIN)

    def test_payloads_and_urls(self):
        wf = alert_channels.teams_payload("workflows", C.Level.CRIT, "T", "x", "https://l")
        self.assertEqual(wf["attachments"][0]["contentType"], "application/vnd.microsoft.card.adaptive")
        self.assertEqual(wf["attachments"][0]["content"]["actions"][0]["url"], "https://l")
        mc = alert_channels.teams_payload("messagecard", C.Level.WARN, "T", "x", "")
        self.assertEqual((mc["@type"], mc["themeColor"]), ("MessageCard", "FFB900"))
        calls = []
        orig = alert_channels._post
        alert_channels._post = lambda url, payload: (calls.append((url, payload)) or (True, "200", {"ok": True}))
        try:
            cfg = FakeSettings().get(with_secrets=True)
            self.assertEqual(alert_channels.send_zalo(cfg, "T", "x", "https://l"), (True, "200"))
            self.assertEqual(calls[0][0], "https://bot-api.zaloplatforms.com/bot1:abc/sendMessage")
            self.assertEqual(calls[0][1]["chat_id"], "g1")
            self.assertEqual(alert_channels.send_teams(dict(cfg, teams_enabled=0), "warn", "T", "x", ""), (False, "OFF"))
            alert_channels._post = lambda url, payload: (True, "200", {"ok": False, "error_code": 401})
            self.assertEqual(alert_channels.send_zalo(cfg, "T", "x", ""), (False, "API:401"))
        finally:
            alert_channels._post = orig


if __name__ == "__main__":
    unittest.main()
