# Copyright (c) 2026, eCentric and contributors
"""Test validate noi tai cua phieu ty trong luong: ky, trung brand, tong = 100.

Doc file nguon that (khong copy logic). Ba thu duoc khoa vi ca ba deu lam PnL sai ma
KHONG sinh loi o bat ky dau: tong != 100 lam bien mat mot phan chi phi; trung brand cho
tong dung nhung phan bo sai; ky go tay lam cung mot thang tach thanh nhieu nhom."""
import importlib.util
import os
import sys
import types
import unittest


class _Throw(Exception):
    pass


def _stub():
    m = types.ModuleType("frappe")
    def _throw(msg, exc=None):
        raise _Throw(msg)
    m.throw = _throw
    m._ = lambda s: s
    utils = types.ModuleType("frappe.utils")
    utils.flt = lambda v, p=2: round(float(v), p)
    m.utils = utils
    sys.modules["frappe"] = m
    sys.modules["frappe.utils"] = utils


_stub()
_SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                    "features", "brand_weight", "application", "validation.py")
_spec = importlib.util.spec_from_file_location("_bw_validation", os.path.abspath(_SRC))
validation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validation)


class _Row:
    def __init__(self, brand, weight, idx=1):
        self.brand, self.weight, self.idx = brand, weight, idx


class _Doc:
    def __init__(self, period="2026-09", rows=None, approval_request=None):
        self.period = period
        self.details = rows if rows is not None else [_Row("FLD-VN", 100, 1)]
        self.approval_request = approval_request
        self.total_weight = None
        self.department = "Service - EC"

    def is_new(self):
        return not self.approval_request

    def get_doc_before_save(self):
        return None


def _run(doc):
    validation.ValidateBrandWeightRequestService().execute(doc)
    return doc


class TestValidate(unittest.TestCase):
    def test_hop_le_thi_ghi_lai_tong(self):
        doc = _run(_Doc(rows=[_Row("FLD-VN", 60, 1), _Row("PAW-VN", 40, 2)]))
        self.assertEqual(doc.total_weight, 100)

    def test_tong_thieu_thi_chan(self):
        """Tong 80 -> 20% chi phi phong do bien mat khoi PnL, khong ai thay."""
        with self.assertRaises(_Throw) as cm:
            _run(_Doc(rows=[_Row("FLD-VN", 60, 1), _Row("PAW-VN", 20, 2)]))
        self.assertIn("phải bằng đúng 100%", str(cm.exception))

    def test_tong_vuot_thi_chan(self):
        with self.assertRaises(_Throw):
            _run(_Doc(rows=[_Row("FLD-VN", 60, 1), _Row("PAW-VN", 60, 2)]))

    def test_sai_so_lam_tron_van_chap_nhan(self):
        """33.33 x3 = 99.99 la lam tron cua Percent, khong phai nhap sai."""
        doc = _run(_Doc(rows=[_Row("A", 33.33, 1), _Row("B", 33.33, 2), _Row("C", 33.34, 3)]))
        self.assertAlmostEqual(doc.total_weight, 100.0, places=2)

    def test_trung_brand_thi_chan_du_tong_dung(self):
        with self.assertRaises(_Throw) as cm:
            _run(_Doc(rows=[_Row("FLD-VN", 40, 1), _Row("FLD-VN", 60, 2)]))
        self.assertIn("hai lần", str(cm.exception))

    def test_ty_trong_khong_duong_thi_chan(self):
        with self.assertRaises(_Throw):
            _run(_Doc(rows=[_Row("FLD-VN", 100, 1), _Row("PAW-VN", 0, 2)]))

    def test_khong_co_dong_nao_thi_chan(self):
        with self.assertRaises(_Throw) as cm:
            _run(_Doc(rows=[]))
        self.assertIn("ít nhất một dòng", str(cm.exception))

    def test_ky_sai_dinh_dang_thi_chan(self):
        for bad in ("09/2026", "T9/2026", "2026-9", "2026-13", "2026", "", "thang 9"):
            with self.assertRaises(_Throw, msg="phai chan: %r" % bad):
                _run(_Doc(period=bad))

    def test_ky_dung_dinh_dang_thi_qua(self):
        for good in ("2026-01", "2026-09", "2026-12"):
            self.assertEqual(_run(_Doc(period=good)).total_weight, 100)


if __name__ == "__main__":
    unittest.main()
