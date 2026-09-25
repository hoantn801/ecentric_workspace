# Copyright (c) 2026, eCentric and contributors
"""Lo B17 - ham dung chung de module khac doc ngay nghi. KHONG import frappe.

Ba thu duoc khoa o day. Ca ba deu la cach cai ham nay co the hong ma khong ai
thay ngay:

1. PHAI LOC CUOI TUAN VA NGAY LE. Neu tra ve ca ngay nghi roi vao thu Bay, ben
   Approval Center se dan "nguoi duyet nghi phep" len mot ho so qua han vi ly do
   hoan toan khac. Sai kieu do khong ai bat duoc, vi nhan van trong hop ly.

2. KHONG DUOC NEM LOI. Ben goi la mot cai nhan tren trang duyet don. Mot loi doc
   du lieu HR khong duoc phep lam trang do trang.

3. KHONG DUOC LA ENDPOINT. Mo `@frappe.whitelist()` o day la day ngay nghi ca
   nhan cua ca cong ty ra truoc trinh duyet ma khong ai can den no.
"""
import ast
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SLA = os.path.join(HERE, "..")


def _read(*parts):
    with io.open(os.path.join(SLA, *parts), encoding="utf-8") as fh:
        return fh.read()


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _block(src, name):
    i = src.index("def %s(" % name)
    rest = src[i:]
    j = rest.find("\ndef ")
    return rest if j < 0 else rest[:j]


class TestHamDungChung(unittest.TestCase):

    def setUp(self):
        self.src = _read("infrastructure", "leave_pause.py")

    def test_hai_ham_deu_cong_khai(self):
        for name in ("working_leave_days", "is_on_leave"):
            self.assertIsNotNone(_fn(self.src, name), "thieu %s" % name)
            self.assertFalse(name.startswith("_"))

    def test_loc_cuoi_tuan_va_ngay_le(self):
        blk = _block(self.src, "working_leave_days")
        self.assertIn("weekday() < 5", blk)
        self.assertIn("holidays", blk)

    def test_khong_nem_loi(self):
        blk = _block(self.src, "working_leave_days")
        self.assertIn("except Exception:", blk)
        self.assertNotIn("raise", blk)

    def test_nhan_ca_chuoi_lan_danh_sach(self):
        blk = _block(self.src, "working_leave_days")
        self.assertIn("isinstance(users, str)", blk)

    def test_luon_tra_du_key_duoc_hoi(self):
        """Ben goi lam `res[user]` truc tiep; thieu key la KeyError tren trang."""
        blk = _block(self.src, "working_leave_days")
        self.assertIn("out[u] = []", blk)

    def test_khong_mo_endpoint(self):
        """Soi DECORATOR, khong soi tu tran: loi giai thich trong tep co quyen
        nhac toi chuyen 'co y khong mo endpoint' ma khong bi coi la vi pham."""
        self.assertNotIn("@frappe.whitelist", self.src)

    def test_dung_lai_ham_doc_cua_nhom_cham_cong(self):
        """Hai dinh nghia 'ngay nghi' trong mot he thong se troi ra xa nhau."""
        blk = _block(self.src, "working_leave_days")
        self.assertIn("att._leave_days", blk)
        self.assertIn("att._holidays_for", blk)

    def test_is_on_leave_dung_lai_working_leave_days(self):
        blk = _block(self.src, "is_on_leave")
        self.assertIn("working_leave_days", blk)

    def test_khong_cham_vao_approval_center(self):
        self.assertNotIn("approval_center", self.src)


if __name__ == "__main__":
    unittest.main()
