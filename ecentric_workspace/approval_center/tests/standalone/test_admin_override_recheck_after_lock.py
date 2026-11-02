# Copyright (c) 2026, eCentric and contributors
"""Duyet thay (admin_override_current_level) phai DOC LAI trang thai phieu SAU khi khoa.

Cung lop loi BOT D (test_e2e2_engine_guard_races.py) da va o approve / reject / cancel /
request_information / resubmit - rieng duong duyet thay cua System Manager bi bo sot: no doc
`approval_status` TRUOC khi lay khoa hang, sau khoa chi kiem `level_status` cua cap.

Ma `cancel()` va `request_information()` KHONG dong cham `level_status` - cap van "In
Progress". Nen neu nguoi de nghi bam Huy (hoac nguoi duyet bam Yeu cau bo sung) dung luc SM
bam Duyet thay: SM doc "Pending", cho khoa, giao dich kia commit, SM di tiep va
  * phieu 1 cap -> complete_approval ghi de "Cancelled" thanh "Approved" (+ goi handler xu ly);
  * phieu dang cho bo sung -> cap bi dong, phieu di tiep ma nguoi de nghi khong hay.

Chay CODE THAT cua transitions.py qua dung harness cua test_e2e2_engine_guard_races.py.
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_races_harness", os.path.join(_HERE, "test_e2e2_engine_guard_races.py"))
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)

AR, RL, AP, ACT = _h.AR, _h.RL, _h.AP, _h.ACT


class TestAdminOverrideDocLaiSauKhoa(unittest.TestCase):

    def _setup(self):
        stub = _h._FrappeStub()
        _h._seed(stub, "All Required")
        return stub, _h._load_engine(stub)

    def test_huy_chen_vao_luc_cho_khoa_thi_duyet_thay_bi_chan(self):
        stub, eng = self._setup()
        # Nguoi de nghi Huy commit dung luc SM dang cho khoa hang.
        stub.on_request_lock = lambda: eng.cancel("AR-1", actor="req@x", reason="khong can nua")
        with self.assertRaises(_h._ValidationError):
            eng.admin_override_current_level("AR-1", actor="sm@x", reason="duyet thay")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Cancelled",
                         "phieu da Huy khong duoc bi ghi de thanh Approved")
        self.assertEqual(stub.store[RL]["RL-1"]["level_status"], "In Progress")
        self.assertEqual(stub.dispatched, [], "khong duoc goi handler xu ly cho phieu da Huy")
        acts = [a["action"] for a in stub.store[ACT].values()]
        self.assertNotIn("Approved", acts)

    def test_yeu_cau_bo_sung_chen_vao_thi_duyet_thay_bi_chan(self):
        stub, eng = self._setup()
        stub.on_request_lock = lambda: eng.request_information(
            "AR-1", actor="a@x", comment="bo sung hoa don")
        with self.assertRaises(_h._ValidationError):
            eng.admin_override_current_level("AR-1", actor="sm@x", reason="duyet thay")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Information Required")
        self.assertEqual(stub.store[AP]["AP-A"]["status"], "Information Requested")
        self.assertEqual(stub.store[AP]["AP-B"]["status"], "Pending")

    def test_doi_chung_duyet_thay_binh_thuong_van_chay(self):
        stub, eng = self._setup()
        eng.admin_override_current_level("AR-1", actor="sm@x", reason="duyet thay")
        self.assertEqual(stub.store[AR]["AR-1"]["approval_status"], "Approved")
        self.assertEqual(stub.store[AP]["AP-A"]["status"], "Skipped")
        self.assertEqual(stub.store[AP]["AP-B"]["status"], "Skipped")


if __name__ == "__main__":
    unittest.main()
