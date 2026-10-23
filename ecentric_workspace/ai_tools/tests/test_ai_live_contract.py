# Copyright (c) 2026, eCentric and contributors
"""fix10g - khop hop dong ERP <-> eC Live 1.0.21 (tai lieu app gui 23/10): on_air la mang object, problems[] cap may,
nhip minimal, anh WEBP, ma phien, khung >= 5 phut, thu tu khung on dinh, lenh co expires_at, crash_resume.
Chay ngoai Frappe."""
import base64
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.pull_commands_service import PullCommandsService
from ecentric_workspace.ai_tools.features.ai_live.application.push_heartbeat_service import decode_thumb
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
from ecentric_workspace.ai_tools.tests.test_ai_live_machine_watch import T0, World
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import live
from ecentric_workspace.ai_tools.tests.test_ai_live_session import MON, FakeCommands, FakeMachines, FakeSessions


class TestHeartbeat1021(unittest.TestCase):
    def test_on_air_objects_and_problems_in_silent_alert(self):
        w = World(T0)
        w.push([live(state="idle", schedule=[])],
               on_air=[{"live": "L1", "brand": "friso", "mode": "camera", "talking": True, "since": "2026-10-19T12:55:00.000Z"}],
               problems=[{"rule": "network_down", "level": "critical", "text": "Mất mạng", "live": None},
                         {"rule": "cpu_high", "level": "warn", "text": "CPU 97%"}])
        self.assertEqual(w.m["hb_lives"], [{"live": "L1", "brand": "friso", "since": 1792414500.0, "mode": "camera"}])
        self.assertEqual(w.m["hb_alerts"], ["Mất mạng (đỏ)", "CPU 97% (vàng)"])
        self.assertEqual(w.at(4).watch(), 1)
        self.assertIn("Báo động khẩn cuối cùng: Mất mạng.", w.last()["text"])

    def test_resume_text_on_back(self):
        w = World(T0)
        w.push()
        w.at(4).watch()
        w.at(6).push(app_started_at=w.clock.t - 30, resume={"resumed_at": "x", "from_crash": True, "lives": ["L1", "L2"],
                                                              "ok": ["L1"], "failed": ["L2"]})
        w.at(1).watch()
        self.assertIn("App eC Live vừa mở lại sau lỗi (máy không khởi động lại). Tự phát tiếp: OK L1 · lỗi L2.", w.last()["text"])

    def test_minimal_keeps_metrics_and_alerts(self):
        w = World(T0)
        w.push([live(alerts=[{"code": "esync_down", "level": "critical", "text": "Mất eSync", "since": 1792420000000}])])
        before = w.health.get("MAY01__L1")
        w.at(1).push([{"live": "L1", "brand": "friso", "name": "L1", "state": "live", "health": "warn"}], minimal=True)
        after = w.health.get("MAY01__L1")
        self.assertEqual(after["metrics"], before["metrics"])
        self.assertEqual([a["code"] for a in after["alerts"] if a["src"] == "app"], ["esync_down"])
        self.assertEqual(after["last_seen_ts"], T0 + 60)

    def test_webp_and_data_url(self):
        webp = b"RIFF" + b"\x10\x00\x00\x00" + b"WEBPVP8 " + b"z" * 20
        self.assertEqual(decode_thumb(base64.b64encode(webp).decode())[1], "webp")
        jpg = b"\xff\xd8\xff\xe0" + b"x" * 10
        self.assertEqual(decode_thumb("data:image/jpeg;base64," + base64.b64encode(jpg).decode())[1], "jpg")

    def test_resume_without_lists_is_empty(self):
        self.assertEqual(W._resume_text({"from_crash": True}), "")


class Doc:
    def __init__(self, **kw):
        self.__dict__.update(dict(live_id="", name="", platform="TikTok", tiktok_username="shop", watch_url="", phone_serial="",
                                  mode="", slots=[], machine="", obs_port=0, enabled=1, brand="friso"), **kw)


class TestSchedule1021(unittest.TestCase):
    def test_session_id_matches_app(self):
        svc = ValidateSessionService(FakeSessions(), FakeMachines(), clock=lambda: MON)
        self.assertEqual(svc.execute(Doc(live_id="friso-toi_1")).live_id, "friso-toi_1")
        for bad in ("friso.toi", "x" * 33, "a b"):
            with self.assertRaises(C.AiLiveError):
                svc.execute(Doc(live_id=bad))

    def test_slot_at_least_5_minutes_and_stable_order(self):
        with self.assertRaises(C.AiLiveError) as cm:
            S.norm_slots([{"days": [1], "start": "19:00", "end": "19:03"}])
        self.assertIn("5 phút", str(cm.exception))
        self.assertEqual(S.norm_slots([{"days": [1], "start": "23:58", "end": "00:03"}])[0]["end"], "00:03")   # qua dem 5'
        out = S.norm_slots([{"date": "2026-10-25", "start": "08:00", "end": "09:00"}, {"days": [1], "start": "19:00", "end": "21:00"},
                            {"days": [1], "start": "09:00", "end": "10:00"}])
        self.assertEqual([(s["date"], s["start"]) for s in out], [(None, "09:00"), (None, "19:00"), ("2026-10-25", "08:00")])

    def test_commands_carry_expiry(self):
        cmds = FakeCommands()
        cmds.insert({"live": "a", "machine": "MAY01", "action": "pause_ai", "args": {}, "created_ts": MON - 10})
        out = PullCommandsService(FakeMachines(), cmds, clock=lambda: MON).execute("u1", "MAY01")["commands"][0]
        self.assertEqual(out["ttl_sec"], C.CMD_TTL_S)
        self.assertEqual((out["created_at"], out["expires_at"]), ("2026-10-19T04:59:50.000Z", "2026-10-19T05:01:50.000Z"))

    def test_crash_resume_summary(self):
        s = S.sanitize_summary({"session": "L1_1", "started_at": MON - 3600, "ended_at": None, "duration_s": 1800,
                                "reason": "crash_resume"}, MON)
        self.assertEqual((s["reason"], s["ended_ts"]), ("crash_resume", MON - 1800))


if __name__ == "__main__":
    unittest.main()
