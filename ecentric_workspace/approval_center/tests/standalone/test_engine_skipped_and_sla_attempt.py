# Copyright (c) 2026, eCentric and contributors
"""Hai loi nho cua engine duyet (QA t1, 03/11/2026) - chay code that cua transitions.py.

1. CAP "All Required" CO DONG Skipped THI KHONG BAO GIO DONG.
   `role_pool.tidy_open_rows` chuyen sang Skipped dong "Role: X" cua nguoi vua mat role
   (hoac co ghe rieng o cap sau) - chi khi cap con nguoi khac Pending. Nhung
   `decide_level("All Required")` doi `approved == total` voi `total` DEM CA dong Skipped:
   moi nguoi con lai duyet het van "pending" -> phieu ket vinh vien, khong ai con nut bam.
   Dong Skipped la nguoi DA BI RUT khoi cap, khong phai nguoi con no phieu.

2. LAM LAI TU CAP 1 MO NGHIA VU SLA CUA VONG MOI BANG SO LAN CU.
   `_sla_attempt` nho ket qua trong frappe.local theo ten phieu. `resubmit(restart=True)`
   goi no TRUOC khi ghi "Restarted" (dung, de ket so vong cu) - roi `_activate_level` cung
   request do hoi lai va nhan lai so CU tu bo nho. Nghia vu cap 1 cua vong moi mang khoa
   chong trung cua vong cu (bi nuot hoac lech so), trong khi lan bam duyet o request sau
   tinh dung so moi -> dong ho cap 1 vong hai khong khop, bien mat khoi bang diem SLA.
"""
import importlib.util
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_e2e2_base_sk", os.path.join(_HERE, "test_e2e2_engine_guard_races.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
AR, RL, AP, ACT = _base.AR, _base.RL, _base.AP, _base.ACT


def _engine(stub):
    eng = _base._load_engine(stub)
    eng.assign = lambda *a, **k: None
    eng.close_todos = lambda *a, **k: None
    eng._luong_co_ky_so = lambda req, ctx: False
    eng._esign_on_reopen = lambda name: {"revised": False, "new_package": None,
                                         "force_restart": False}
    stub.log_error = lambda *a, **k: None
    return eng


class TestAllRequiredBoQuaDongSkipped(unittest.TestCase):

    def setUp(self):
        self.eng = _engine(_base._FrappeStub())

    def test_skipped_khong_tinh_vao_tong(self):
        self.assertEqual(self.eng.decide_level("All Required", 0, ["Skipped", "Approved", "Approved"]),
                         ("approved", False))

    def test_con_nguoi_pending_thi_chua_xong(self):
        self.assertEqual(self.eng.decide_level("All Required", 0, ["Skipped", "Approved", "Pending"]),
                         ("pending", False))

    def test_toan_skipped_khong_tu_dong_cap(self):
        """Khong ai duyet thi khong duoc coi la da duyet (role_pool luon giu nguoi cuoi)."""
        self.assertEqual(self.eng.decide_level("All Required", 0, ["Skipped", "Skipped"]),
                         ("pending", False))

    def test_doi_chung_tu_choi_van_thang(self):
        self.assertEqual(self.eng.decide_level("All Required", 0, ["Skipped", "Rejected"]),
                         ("rejected", False))

    def test_kich_ban_mat_role_roi_hai_nguoi_con_lai_duyet(self):
        stub = _base._FrappeStub()
        eng = _engine(stub)
        _base._seed(stub, "All Required")
        stub.store[AP]["AP-C"] = {"name": "AP-C", "approval_request": "AR-1", "level_no": 1,
                                  "approver": "c@x", "status": "Skipped"}   # role_pool rut ra
        eng.approve("AR-1", actor="a@x")
        eng.approve("AR-1", actor="b@x")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved",
                         "hai nguoi con lai da duyet het ma phieu van ket")


class TestSlaAttemptSauKhiLamLai(unittest.TestCase):

    def test_vong_moi_mo_nghia_vu_bang_so_lan_moi(self):
        stub = _base._FrappeStub()
        eng = _engine(stub)
        _base._seed(stub, "Any One")
        stub.store[AR]["AR-1"].update({"approval_status": "Information Required",
                                       "information_requested_from_level": 1})
        stub.store[RL]["RL-1"]["sla_policy"] = None
        stub.store["Employee"] = {}
        calls = []
        eng._sla = lambda: types.SimpleNamespace(
            on_request_restarted=lambda **k: calls.append(("restarted", k["attempt"])),
            on_resubmitted=lambda **k: calls.append(("resubmitted", k["attempt"])),
            on_level_activated=lambda **k: calls.append(("activated", k["attempt"])))
        eng.resubmit("AR-1", actor="req@x", restart=True)
        self.assertIn(("restarted", 1), calls, "ket so vong CU = lan 1")
        self.assertIn(("activated", 2), calls,
                      "cap 1 cua vong MOI phai mo nghia vu lan 2, khong phai lan 1 (%r)" % calls)
        # Va mot lan doc moi (request sau) cung ra 2 - hai noi phai khop nhau.
        stub.local._ec_sla_attempt = {}
        self.assertEqual(eng._sla_attempt("AR-1"), 2)


if __name__ == "__main__":
    unittest.main()
