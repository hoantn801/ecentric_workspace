# Copyright (c) 2026, eCentric and contributors
"""Phong live (spec muc 7): list_rooms, heartbeat ghi phong + canh bao trung, next_session theo phong,
session_open nhan phien theo phong / no_schedule, kiem mic theo may dang khai phong."""
import datetime as dt
import types
import unittest

from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.get_next_session_service import GetNextSessionService
from ecentric_workspace.host_qc.services.list_rooms_service import ListRoomsService
from ecentric_workspace.host_qc.services.machine_mics_service import MachineMicsService
from ecentric_workspace.host_qc.services.open_session_service import OpenSessionService
from ecentric_workspace.host_qc.services.record_heartbeat_service import RecordHeartbeatService
from ecentric_workspace.host_qc.services.validate_room_service import ValidateRoomService
from ecentric_workspace.host_qc.services.validate_session_service import ValidateSessionService
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService
from ecentric_workspace.host_qc.tests import fakes as F

M1, M2 = {"name": "M1", "machine_id": "M1"}, {"name": "M2", "machine_id": "M2"}


class Banned:
    def for_platform(self, p):
        return []


class TestRooms(unittest.TestCase):
    def setUp(self):
        self.m, self.rooms, self.st = F.FakeMachines(), F.FakeRooms(), F.FakeSettings()
        for mid in ("M1", "M2"):
            self.m.add(mid)
        self.hb = RecordHeartbeatService(self.m, self.st, self.rooms, clock=F.clock)

    def test_list_rooms_chi_phong_dang_hoat_dong_kem_brand_cua_phien(self):
        s = F.FakeSessions()
        s.add("sap-toi", machine=None, live_room="P1", planned_start=F.NOW + dt.timedelta(hours=2),
              platform="shopee", tiktok_username="", brand="Brand B")
        s.add("dang-chay", machine="M1", live_room="P1", status="Running", planned_start=F.NOW - dt.timedelta(minutes=20),
              platform="tiktok", tiktok_username="vinasoy.official", brand="Vinasoy")
        s.add("hom-qua", machine=None, live_room="P2", planned_start=F.NOW - dt.timedelta(days=1))
        self.assertEqual(ListRoomsService(self.rooms, s, F.clock).execute(),
                         [{"id": "P1", "name": "Phòng 1", "platform": "tiktok", "shop": "vinasoy.official"},
                          {"id": "P2", "name": "Phòng 2", "platform": "", "shop": ""}])

    def test_heartbeat_ghi_phong_va_canh_bao_trung(self):
        self.hb.execute(M1, {"room_id": "P1"})
        self.assertEqual((self.m.hb["M1"]["current_room"], self.m.hb["M1"]["room_warning"]), ("P1", ""))
        self.hb.execute(M2, {"room_id": "P1"})
        self.assertEqual(self.m.hb["M2"]["current_room"], "P1")
        self.assertIn("M1", self.m.hb["M2"]["room_warning"])
        self.hb.execute(M2, {"room_id": "P9"})                              # phong da ngung
        self.assertIsNone(self.m.hb["M2"]["current_room"])
        self.assertIn("P9", self.m.hb["M2"]["room_warning"])

    def test_heartbeat_khong_gui_room_thi_giu_nguyen(self):
        self.hb.execute(M1, {"room_id": "P1"})
        self.hb.execute(M1, {"state": "idle"})
        self.assertNotIn("current_room", self.m.hb["M1"])                   # khong ghi de phong da chon

    def test_ma_phong(self):
        doc = types.SimpleNamespace(room_id=" Phong 1.A ")
        ValidateRoomService().execute(doc)
        self.assertEqual(doc.room_id, "Phong 1.A")
        with self.assertRaises(InvalidInput):
            ValidateRoomService().execute(types.SimpleNamespace(room_id="Phòng 1"))


class TestSessionByRoom(unittest.TestCase):
    def setUp(self):
        self.s, self.m = F.FakeSessions(), F.FakeMachines()
        self.m.add("M1")
        self.st = F.FakeSettings()
        self.next = GetNextSessionService(self.s, Banned(), self.st, BuildRulesConfigService(self.st, F.FakeRules()), F.clock)
        self.open = OpenSessionService(self.s, self.m, F.FakeRooms(), F.clock, RescoreSessionService(self.s, F.FakeViolations(), BuildRulesConfigService(F.FakeSettings(), F.FakeRules())))

    def test_next_session_theo_phong(self):
        self.s.add("p1-toi", machine=None, live_room="P1", planned_start=F.NOW + dt.timedelta(minutes=5))
        self.s.add("p1-may-khac", machine="M2", live_room="P1", planned_start=F.NOW)
        self.s.add("p2", machine=None, live_room="P2", planned_start=F.NOW)
        cfg = self.next.execute(M1, "P1")
        self.assertEqual((cfg["session_id"], cfg["room_id"]), ("p1-toi", "P1"))
        self.assertIsNone(self.next.execute(M1, "P3"))
        self.assertIsNone(self.next.execute(M1))                           # khong phong -> theo may: khong co

    def test_mo_phien_theo_phong_thi_gan_may(self):
        self.s.add("p1-toi", machine=None, live_room="P1")
        self.open.execute(M1, {"session_id": "p1-toi", "room_id": "P1"})
        self.assertEqual((self.s.s["p1-toi"]["machine"], self.s.s["p1-toi"]["status"]), ("M1", "Running"))
        with self.assertRaises(ForbiddenError):
            self.open.execute(M2, {"session_id": "p1-toi"})

    def test_no_schedule(self):
        cfg = {"hosts": [{"host_id": "h1", "name": "Chưa rõ host (mic 1)", "mic_device": "Rode A"}]}
        self.open.execute(M1, {"session_id": "nosched-1", "room_id": "P1", "no_schedule": "true", "config": cfg})
        vals, _ = self.s.created[0]
        self.assertEqual((vals["live_room"], vals["no_schedule"], vals["source"]), ("P1", 1, "unplanned"))
        self.open.execute(M1, {"session_id": "nosched-2", "room_id": "khong-co", "no_schedule": True, "config": cfg})
        self.assertIsNone(self.s.created[1][0]["live_room"])


def sdoc(**kw):
    d = dict({"session_id": "s1", "planned_start": "2026-11-24 20:00:00", "planned_end": "2026-11-24 22:00:00",
              "machine": None, "live_room": None, "hosts": []}, **kw)
    doc = types.SimpleNamespace(**d)
    doc.flags = types.SimpleNamespace(from_machine=False)
    doc.get = lambda k: getattr(doc, k, None)
    return doc


class TestValidateByRoom(unittest.TestCase):
    def test_mic_theo_may_dang_khai_phong(self):
        m = F.FakeMachines()
        m.add("M1")
        m.add_mic("M1", 1, "Rode A", "WASAPI", 1, F.NOW)
        v = ValidateSessionService(m)
        h = types.SimpleNamespace(host_id="h1", mic_device="Mic la")
        v.execute(sdoc(live_room="P1", hosts=[h]))                         # chua may nao khai phong -> chua kiem
        m.hb["M1"] = {"current_room": "P1", "last_seen": F.NOW}
        with self.assertRaises(InvalidInput):
            v.execute(sdoc(live_room="P1", hosts=[h]))
        h.mic_device = "Rode A"
        v.execute(sdoc(live_room="P1", hosts=[h]))
        self.assertEqual([x["device_name"] for x in MachineMicsService(m, F.clock).execute(["Host QC Viewer"], None, "P1")],
                         ["Rode A"])
        with self.assertRaises(InvalidInput):
            v.execute(sdoc())                                              # khong phong, khong may


if __name__ == "__main__":
    unittest.main()
