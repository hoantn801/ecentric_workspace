# Copyright (c) 2026, eCentric and contributors
"""Lay phien theo lich, mo phien (ca ngoai lich), dong phien, kiem cau hinh phien, canh bao, rules_version."""
import datetime as dt
import types
import unittest

from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.bump_rules_version_service import BumpRulesVersionService
from ecentric_workspace.host_qc.services.close_session_service import CloseSessionService
from ecentric_workspace.host_qc.services.get_next_session_service import GetNextSessionService
from ecentric_workspace.host_qc.services.open_session_service import OpenSessionService
from ecentric_workspace.host_qc.services.record_alert_service import RecordAlertService
from ecentric_workspace.host_qc.services.validate_session_service import ValidateSessionService
from ecentric_workspace.host_qc.tests import fakes as F

M1 = {"name": "M1", "machine_id": "M1"}


class Banned:
    def for_platform(self, p):
        return [{"kind": "commitment", "phrase": "chữa khỏi"}]


class Noop:
    def execute(self, *a, **k):
        return None


class TestNextSession(unittest.TestCase):
    def setUp(self):
        self.s = F.FakeSessions()
        st = F.FakeSettings()
        self.svc = GetNextSessionService(self.s, Banned(), st, BuildRulesConfigService(st, F.FakeRules()), F.clock)

    def test_chon_phien_gan_nhat_cua_dung_may(self):
        self.s.add("xa", planned_start=F.NOW - dt.timedelta(minutes=50))
        self.s.add("gan", planned_start=F.NOW + dt.timedelta(minutes=10),
                   hosts=[{"host_id": "h1", "host_name": "Lan", "role": "main", "mic_device": "Rode A", "on_camera": 1}],
                   banned_phrases=[{"kind": "offensive", "phrase": "xx"}],
                   rule_overrides=[{"code": "SAL-01", "key": "gap_min", "value": 7.0}])
        self.s.add("may-khac", machine="M2", planned_start=F.NOW)
        self.s.add("qua-som", planned_start=F.NOW + dt.timedelta(minutes=45))
        self.s.add("da-chay", status="Running", planned_start=F.NOW)
        cfg = self.svc.execute(M1)
        self.assertEqual(cfg["session_id"], "gan")
        self.assertEqual(cfg["hosts"][0]["mic_device"], "Rode A")
        self.assertEqual(cfg["banned"], {"commitment": ["chữa khỏi"], "offensive": ["xx"]})
        self.assertEqual(cfg["rules"], {"codes": {"SAL-01": {"gap_min": 7}}})
        self.assertEqual(cfg["ai"]["kie_api_key"], "kie-secret")
        self.assertEqual(cfg["rules_config"]["version"], "v1")

    def test_khong_co_phien(self):
        self.s.add("may-khac", machine="M2")
        self.assertIsNone(self.svc.execute(M1))


class TestOpenClose(unittest.TestCase):
    def setUp(self):
        self.s, self.m = F.FakeSessions(), F.FakeMachines()
        self.m.add("M1")
        self.open = OpenSessionService(self.s, self.m, F.clock)

    def test_phien_theo_lich(self):
        self.s.add("s1")
        self.open.execute(M1, {"session_id": "s1", "started_at": 1795957200000, "config_hash": "h", "app_version": "0.1"})
        self.assertEqual(self.s.s["s1"]["status"], "Running")
        self.assertEqual(self.m.current["M1"], "s1")
        with self.assertRaises(ForbiddenError):
            self.open.execute({"name": "M2"}, {"session_id": "s1"})

    def test_phien_ngoai_lich_tao_tu_config(self):
        cfg = {"title": "Test", "platform": "shopee", "format": "kol",
               "hosts": [{"host_id": "h1", "name": "Lan", "mic_device": "Rode A"}],
               "products": [{"code": "P1", "name": "Kem", "aliases": ["kem a", "kem b"], "usp": ["mịn"]}],
               "deals": [{"id": "d1", "text": "2 tặng 1", "keywords": ["2 tặng 1"], "important": True}],
               "banned": {"commitment": ["chữa khỏi"]},
               "scripted_silences": [{"from": 1795957200000, "to": 1795957260000}, {"from": "x"}]}
        self.open.execute(M1, {"session_id": "ngoai-lich", "started_at": 1795957200000, "config": cfg})
        vals, from_machine = self.s.created[0]
        self.assertTrue(from_machine)
        self.assertEqual((vals["source"], vals["platform"], vals["format"]), ("unplanned", "shopee", "kol"))
        self.assertEqual(vals["products"][0]["aliases"], "kem a\nkem b")
        self.assertEqual(len(vals["scripted_silences"]), 1)
        with self.assertRaises(NotFoundError):
            self.open.execute(M1, {"session_id": "chua-co"})
        with self.assertRaises(InvalidInput):
            self.open.execute(M1, {"session_id": "Sai Ma"})

    def test_dong_roi_khong_mo_lai(self):
        self.s.add("s1")
        self.m.current["M1"] = "s1"
        CloseSessionService(self.s, self.m, files=None, rescore=Noop(), clock=F.clock).execute(
            M1, {"session_id": "s1", "summary": "ok", "recommendations": ["a", "b"], "score": {"total": 90}})
        self.assertEqual((self.s.s["s1"]["status"], self.s.s["s1"]["recommendations"]), ("Closed", "a\nb"))
        self.assertIsNone(self.m.current["M1"])
        self.open.execute(M1, {"session_id": "s1"})
        self.assertEqual(self.s.s["s1"]["status"], "Closed")


def sdoc(**kw):
    d = dict({"session_id": "s1", "planned_start": "2026-11-24 20:00:00", "planned_end": "2026-11-24 22:00:00",
              "machine": "M1", "hosts": []}, **kw)
    doc = types.SimpleNamespace(**d)
    doc.flags = types.SimpleNamespace(from_machine=kw.get("from_machine", False))
    doc.get = lambda k: getattr(doc, k, None)
    return doc


def host(hid, mic=""):
    return types.SimpleNamespace(host_id=hid, mic_device=mic)


class TestValidateSession(unittest.TestCase):
    def setUp(self):
        self.m = F.FakeMachines()
        self.m.add("M1")
        self.m.add_mic("M1", 1, "Rode A", "WASAPI", 1, F.NOW)
        self.v = ValidateSessionService(self.m)

    def test_hop_le(self):
        self.v.execute(sdoc(hosts=[host("h1", "Rode A"), host("h2")]))

    def test_cac_loi(self):
        for d in (sdoc(session_id="Sai Ma"), sdoc(planned_end="2026-11-24 19:00:00"),
                  sdoc(hosts=[host("h1"), host("h1")]), sdoc(hosts=[host("h1", "Rode A"), host("h2", "Rode A")]),
                  sdoc(hosts=[host("h1", "Mic la")])):
            with self.assertRaises(InvalidInput):
                self.v.execute(d)

    def test_phien_do_may_tao_khong_kiem_mic_tren_may(self):
        self.v.execute(sdoc(hosts=[host("h1", "Mic la")], from_machine=True))


class TestAlertAndVersion(unittest.TestCase):
    def test_canh_bao_khong_gui_trung(self):
        s, logs = F.FakeSessions(), F.FakeLogs()
        s.add("s1")
        svc = RecordAlertService(s, logs, F.clock)
        self.assertEqual(svc.execute(M1, "s1", "critical", ["v2", "v1"], {"total": 62}), {"sent": False})
        self.assertEqual(svc.execute(M1, "s1", "critical", ["v1", "v2"], 62), {"sent": False, "duplicate": True})
        self.assertEqual(len(logs.rows), 1)
        with self.assertRaises(InvalidInput):
            svc.execute(M1, "s1", "linh tinh", [], 0)

    def test_doi_rules_version(self):
        st = F.FakeSettings()
        v = BumpRulesVersionService(st, F.clock).execute()
        self.assertEqual(st.d["rules_version"], v)
        doc = types.SimpleNamespace(rules_version="")
        BumpRulesVersionService(st, lambda: F.NOW + dt.timedelta(seconds=1)).execute(doc)
        self.assertGreater(doc.rules_version, v)


if __name__ == "__main__":
    unittest.main()
