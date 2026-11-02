# Copyright (c) 2026, eCentric and contributors
"""Cap "All Required" khong duoc ket vinh vien vi mot dong da bi Skipped.

role_pool.tidy_open_rows (25/09) chuyen sang "Skipped" dong Pending "Role: X" cua nguoi vua
mat role (hoac co ghe rieng o cap sau), va chu dong giu lai IT NHAT mot nguoi Pending de cap
khong rong. Nhung decide_level("All Required") dem `approved == total` voi total GOM CA dong
Skipped: ba nguoi A, B, C; C bi go role -> Skipped; A, B duyet -> 2 != 3 -> "pending" mai mai.
Phieu ket o cap do, khong con ai co nut bam (A, B da duyet; C khong con dong Pending).

Chay CODE THAT cua transitions.py qua harness cua test_e2e2_engine_guard_races.py.
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_races_harness", os.path.join(_HERE, "test_e2e2_engine_guard_races.py"))
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)

AR, AP = _h.AR, _h.AP


class TestAllRequiredBoQuaDongSkipped(unittest.TestCase):

    def setUp(self):
        self.stub = _h._FrappeStub()
        _h._seed(self.stub, "All Required")
        self.stub.store[AP]["AP-C"] = {
            "name": "AP-C", "approval_request": "AR-1", "level_no": 1,
            "approver": "c@x", "status": "Pending", "source": "Role: EC Finance",
        }
        self.eng = _h._load_engine(self.stub)

    def test_decide_level_khong_tinh_dong_skipped(self):
        d = self.eng.decide_level
        self.assertEqual(d("All Required", 0, ["Approved", "Approved", "Skipped"]),
                         ("approved", False))
        self.assertEqual(d("All Required", 0, ["Approved", "Pending", "Skipped"]),
                         ("pending", False))
        # Doi chung: khong co dong song nao thi KHONG tu duyet.
        self.assertEqual(d("All Required", 0, ["Skipped", "Skipped"]), ("pending", False))
        self.assertEqual(d("All Required", 0, []), ("pending", False))
        self.assertEqual(d("All Required", 0, ["Approved", "Rejected", "Skipped"]),
                         ("rejected", False))

    def test_phieu_di_tiep_khi_nguoi_con_lai_da_duyet(self):
        # C mat role -> role_pool chuyen dong cua C sang Skipped (A, B con Pending).
        self.stub.store[AP]["AP-C"]["status"] = "Skipped"
        self.eng.approve("AR-1", actor="a@x")
        self.assertEqual(self.stub.store[AR]["AR-1"]["approval_status"], "Pending")
        self.eng.approve("AR-1", actor="b@x")
        self.assertEqual(self.stub.store[AR]["AR-1"]["approval_status"], "Approved",
                         "A va B (moi nguoi con nghia vu) da duyet - cap phai xong")

    def test_doi_chung_con_nguoi_pending_thi_chua_xong(self):
        self.eng.approve("AR-1", actor="a@x")
        self.eng.approve("AR-1", actor="b@x")
        self.assertEqual(self.stub.store[AR]["AR-1"]["approval_status"], "Pending",
                         "C chua duyet va chua bi bo -> cap All Required phai cho")


if __name__ == "__main__":
    unittest.main()
