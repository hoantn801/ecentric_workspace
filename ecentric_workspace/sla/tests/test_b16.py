# Copyright (c) 2026, eCentric and contributors
"""Lo B16 - nghi phep dung dong ho cua nhom Phe duyet. KHONG import frappe.

Hai thu duoc khoa o day, ca hai deu tung sai that tren ban song:

1. CHI DUNG DONG HO CHO NGAY LAM VIEC. Cuoi tuan va ngay le thi han von da khong
   chay qua; cam them mot doan tam dung nua la cho khong hai lan, va no chi sai
   theo mot huong - co loi cho nguoi duoc cham diem, nen khong ai bao.

2. DAU VIEC DA DONG PHAI DUOC CHAM LAI. Doan tam dung cam sau khi da dong thi
   `status` van la gia tri chot luc dong. Khong cham lai thi bay dong da bi cham
   Tre hom 21/09 se nam nguyen - tuc la sua luat ma khong sua hau qua.
"""
import ast
import io
import os
import re
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


class TestLeavePause(unittest.TestCase):

    def setUp(self):
        self.src = _read("infrastructure", "leave_pause.py")

    def test_dung_ly_do_co_san(self):
        """`PAUSE_ABSENCE` da co trong hang so tu dau - khong duoc de ra ly do moi."""
        self.assertIn("PAUSE_ABSENCE", self.src)
        self.assertNotIn('reason="', self.src.replace('reason": PAUSE_ABSENCE', ''))

    def test_bo_qua_cuoi_tuan_va_ngay_le(self):
        body = self.src[self.src.index("def _sync_one("):]
        body = body[:body.index("\ndef ")]
        self.assertIn("weekday() >= 5", body)
        self.assertIn("holidays", body)

    def test_co_cham_lai_dau_viec_da_dong(self):
        self.assertIsNotNone(_fn(self.src, "_reclassify"))
        blk = self.src[self.src.index("def _reclassify("):]
        blk = blk[:blk.index("\ndef ")]
        self.assertIn("classify_close", blk)
        self.assertIn("STATUS_MET", blk)
        self.assertIn("STATUS_LATE", blk)

    def test_cham_lai_dung_thuoc_do_cua_luc_dong(self):
        """Do tre bang mot phep do thu hai se tao ra hai dinh nghia 'tre'."""
        blk = self.src[self.src.index("def _reclassify("):]
        blk = blk[:blk.index("\ndef ")]
        self.assertIn("_elapsed_fn_for", blk)

    def test_chay_lai_duoc(self):
        """Phai kiem doan da ton tai truoc khi chen."""
        self.assertIsNotNone(_fn(self.src, "_has_segment"))
        body = self.src[self.src.index("def _sync_one("):]
        body = body[:body.index("\ndef ")]
        self.assertIn("_has_segment", body)

    def test_co_tran_khi_tim_ngay_lam_viec_ke_tiep(self):
        """Mot lich nghi cau hinh sai co the lam moi ngay deu la ngay nghi."""
        blk = self.src[self.src.index("def _next_work_start("):]
        blk = blk[:blk.index("\ndef ")]
        self.assertIn("_MAX_SKIP", blk)

    def test_preview_khong_ghi_gi(self):
        blk = self.src[self.src.index("def preview("):]
        for bad in ("start_pause", "end_pause", "set_value", "_reclassify"):
            self.assertNotIn(bad, blk, "preview khong duoc ghi: thay %s" % bad)

    def test_moi_nguoi_mot_savepoint(self):
        blk = self.src[self.src.index("def sync("):]
        blk = blk[:blk.index("\ndef preview(")]
        self.assertIn("savepoint", blk)
        self.assertIn("rollback", blk)

    def test_patch_fail_safe(self):
        src = _read("patches", "p014_leave_pause_backfill.py")
        body = src[src.index("def execute():"):]
        self.assertIn("except Exception:", body)
        self.assertNotIn("raise", body)


class TestNgayLamViecKeTiep(unittest.TestCase):
    """Doan tam dung phai keo toi dau ngay lam viec ke tiep, va cac doan lien
    tiep KHONG duoc chong nhau."""

    def _load(self):
        import datetime as dt
        src = _read("infrastructure", "leave_pause.py")
        ns = {"datetime": dt, "_MAX_SKIP": 30}
        blk = src[src.index("def _next_work_start("):]
        blk = blk[:blk.index("\ndef ")]
        exec(compile(blk, "leave_pause", "exec"), ns)
        return ns["_next_work_start"], dt

    def test_nghi_thu_hai_thi_doan_dai_1_ngay(self):
        f, dt = self._load()
        # 2026-09-21 la thu Hai
        out = f(dt.date(2026, 9, 21), set())
        self.assertEqual(out, dt.datetime(2026, 9, 22))

    def test_nghi_thu_sau_thi_doan_keo_qua_cuoi_tuan(self):
        f, dt = self._load()
        # 2026-09-25 la thu Sau -> ngay lam viec ke tiep la thu Hai 28/09
        out = f(dt.date(2026, 9, 25), set())
        self.assertEqual(out, dt.datetime(2026, 9, 28))

    def test_ngay_le_cung_bi_nhay_qua(self):
        f, dt = self._load()
        out = f(dt.date(2026, 9, 21), {dt.date(2026, 9, 22)})
        self.assertEqual(out, dt.datetime(2026, 9, 23))

    def test_hai_ngay_nghi_lien_tiep_khong_chong_nhau(self):
        f, dt = self._load()
        d1, d2 = dt.date(2026, 9, 21), dt.date(2026, 9, 22)
        end1 = f(d1, set())
        start2 = dt.datetime(d2.year, d2.month, d2.day)
        self.assertEqual(end1, start2,
                         "doan cua ngay truoc phai ket thuc dung luc doan sau bat dau")


if __name__ == "__main__":
    unittest.main()
