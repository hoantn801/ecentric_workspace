# Copyright (c) 2026, eCentric and contributors
"""Ham thuan cua phieu ty trong: doc payload HTTP, ky truoc, dong audit, map trang thai.
Doc file nguon that, khong copy logic."""
import importlib.util
import os
import unittest

_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "features", "brand_weight")


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.abspath(os.path.join(_BASE, rel)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


weights = _load("application/weights.py", "_bw_weights")
status = _load("domain/status.py", "_bw_status")


class TestWeights(unittest.TestCase):
    def test_doc_dau_phay_thap_phan_kieu_viet(self):
        """Nguoi dung go '33,5' - doc sai thanh 0 la mat 33,5% ma khong ai bao."""
        self.assertEqual(weights.parse_weights('{"FLD-VN": "33,5", "PAW-VN": 66.5}'),
                         {"FLD-VN": 33.5, "PAW-VN": 66.5})

    def test_bo_dong_rong_va_bang_khong(self):
        self.assertEqual(weights.parse_weights({"A": 0, " ": 10, "B": "abc", "C": 100}), {"C": 100.0})

    def test_payload_khong_phai_object_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            weights.parse_weights("[1, 2]")

    def test_ky_truoc_qua_nam(self):
        self.assertEqual(weights.prev_period("2026-01"), "2025-12")
        self.assertEqual(weights.prev_period("2026-10"), "2026-09")

    def test_so_sanh_bo_qua_dong_bang_khong(self):
        self.assertTrue(weights.same({"A": 50, "B": 50}, {"A": 50.0, "B": "50", "C": 0}))
        self.assertFalse(weights.same({"A": 50, "B": 50}, {"A": 60, "B": 40}))

    def test_dong_audit_ghi_du_ba_kieu_chinh(self):
        txt = weights.diff_text({"FLD-VN": 45, "STL-VN": 15, "PAW-VN": 40},
                                {"FLD-VN": 50, "ABBOTT": 10, "PAW-VN": 40})
        self.assertEqual(txt, "ABBOTT moi 10; FLD-VN 45->50; STL-VN bo (15)")


class TestStatus(unittest.TestCase):
    def test_bang_trang_thai(self):
        s = status.status_of
        self.assertEqual(s(None), "none")
        self.assertEqual(s({"approval_status": None}), "draft")
        self.assertEqual(s({"approval_status": "Pending", "current_level": 1}), "wait_lead")
        self.assertEqual(s({"approval_status": "Information Required"}), "returned")
        self.assertEqual(s({"approval_status": "Approved"}), "final")
        self.assertEqual(s({"approval_status": "Cancelled"}), "cancelled")
        self.assertEqual(s({"approval_status": "Rejected"}), "rejected")

    def test_phieu_bo_cap_1_van_hien_cho_truong_phong(self):
        """CEO khong co lead: phieu vao thang cap 2, phai hien 'cho truong phong'."""
        self.assertEqual(status.status_of({"approval_status": "Pending", "current_level": 2}), "wait_head")
        self.assertEqual(status.stage_of_level(2), "head")
        self.assertEqual(status.stage_of_level(1), "lead")


class TestTrangKhongVoJinja(unittest.TestCase):
    def test_khong_co_chuoi_mo_dong_the_jinja(self):
        """Web Page render qua Jinja. Mot chuoi '{#' trong CSS (vd '){#root') mo comment va
        nuot ca nua duoi trang, khong bao loi. tools/ci/check.py KHONG quet Web Page."""
        import re
        path = os.path.abspath(os.path.join(_BASE, "ui", "main_section.html"))
        html = open(path, encoding="utf-8").read()
        self.assertEqual([], re.findall(r"\{\{|\{%|\{#|#\}|%\}", html))


if __name__ == "__main__":
    unittest.main()
