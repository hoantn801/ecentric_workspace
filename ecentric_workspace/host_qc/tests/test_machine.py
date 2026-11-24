# Copyright (c) 2026, eCentric and contributors
"""Token may (X-HostQC-Token), nhip, micro tren may."""
import datetime as dt
import unittest

from ecentric_workspace.host_qc.exceptions import AuthError, ForbiddenError, InvalidInput, TooManyAttempts
from ecentric_workspace.host_qc.services.issue_machine_token_service import IssueMachineTokenService
from ecentric_workspace.host_qc.services.machine_mics_service import MachineMicsService
from ecentric_workspace.host_qc.services.record_heartbeat_service import RecordHeartbeatService
from ecentric_workspace.host_qc.services.validate_machine_service import ValidateMachineService
from ecentric_workspace.host_qc.services.verify_machine_token_service import VerifyMachineTokenService
from ecentric_workspace.host_qc.tests import fakes as F


class Doc(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class TestToken(unittest.TestCase):
    def setUp(self):
        self.m, self.att = F.FakeMachines(), F.FakeAttempts()
        self.m.add("STUDIO.01")
        self.tok = IssueMachineTokenService(self.m, F.clock).execute("STUDIO.01", "qc@x", ["Host QC Manager"])["token"]
        self.v = VerifyMachineTokenService(self.m, self.att)

    def test_token_dung(self):
        self.assertEqual(self.v.execute("STUDIO.01.%s" % self.tok, "1.1.1.1")["name"], "STUDIO.01")
        self.assertNotIn(self.tok, str(self.m.m))                      # chi luu bam

    def test_token_sai_thieu_tat_may(self):
        for h in ("", "STUDIO.01.sai", "KHAC.%s" % self.tok, self.tok):
            with self.assertRaises(AuthError):
                self.v.execute(h, "1.1.1.1")
        self.m.m["STUDIO.01"]["enabled"] = 0
        with self.assertRaises(AuthError):
            self.v.execute("STUDIO.01.%s" % self.tok, "2.2.2.2")

    def test_sai_qua_nhieu_chan_ca_token_dung(self):
        for _ in range(30):
            with self.assertRaises(AuthError):
                self.v.execute("STUDIO.01.sai", "9.9.9.9")
        with self.assertRaises(TooManyAttempts):
            self.v.execute("STUDIO.01.%s" % self.tok, "9.9.9.9")

    def test_cap_token_can_manager(self):
        with self.assertRaises(ForbiddenError):
            IssueMachineTokenService(self.m).execute("STUDIO.01", "u", ["Host QC Viewer"])

    def test_tao_token_moi_lam_token_cu_het_han(self):
        IssueMachineTokenService(self.m, F.clock).execute("STUDIO.01", "qc@x", ["System Manager"])
        with self.assertRaises(AuthError):
            self.v.execute("STUDIO.01.%s" % self.tok, "1.1.1.1")

    def test_ma_may(self):
        ValidateMachineService().execute(Doc(machine_id=" STUDIO-2 "))
        with self.assertRaises(InvalidInput):
            ValidateMachineService().execute(Doc(machine_id="studio 2"))


class TestHeartbeat(unittest.TestCase):
    def test_gop_mic_khong_xoa(self):
        m = F.FakeMachines()
        m.add("M1")
        m.add_mic("M1", 1, "Mic cu", "WASAPI", 1, F.NOW - dt.timedelta(hours=3))
        svc = RecordHeartbeatService(m, F.FakeSettings(), F.FakeRooms(), clock=F.clock)
        out = svc.execute({"name": "M1"}, {"app_version": "0.1.0", "state": "idle", "load_level": "2",
                                           "obs": {"connected": True, "skipped_pct": 0.5},
                                           "audio_inputs": [{"name": "Rode A", "hostapi": "WASAPI", "channels": 2},
                                                            {"name": "Rode A", "hostapi": "WASAPI", "channels": 2},
                                                            {"name": ""}]})
        self.assertEqual(out, {"rules_version": "v1", "server_time": "2026-11-24T20:00:00+07:00"})
        self.assertEqual([r["device_name"] for r in m.mic_rows["M1"]], ["Mic cu", "Rode A"])
        self.assertEqual((m.hb["M1"]["load_level"], m.hb["M1"]["obs_connected"]), (2, 1))
        mics = MachineMicsService(m, F.clock).execute(["Host QC Viewer"], "M1")
        self.assertEqual([(x["device_name"], x["stale"]) for x in mics], [("Mic cu", True), ("Rode A", False)])
        with self.assertRaises(ForbiddenError):
            MachineMicsService(m, F.clock).execute(["Employee"], "M1")



class TestGuardMessage(unittest.TestCase):
    def test_sai_ma_may_noi_ro(self):
        from ecentric_workspace.host_qc.constants import messages as M
        self.assertIn("TEST-2", M.MACHINE_ID_MISMATCH % ("TEST-2", "TEST-1"))


if __name__ == "__main__":
    unittest.main()
