# Copyright (c) 2026, eCentric and contributors
"""Ba thu cua lo B15. KHONG import frappe - doc bang van ban va AST."""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SLA = os.path.join(HERE, "..")


def _read(*parts):
    with io.open(os.path.join(SLA, *parts), encoding="utf-8") as fh:
        return fh.read()


def _page():
    src = _read("pages", "scoreboard", "main_section.html")
    m = re.search(r"<script id=\"ec-sla-scoreboard\">(.*?)</script>", src, re.S)
    assert m, "khong tim thay khoi script cua trang"
    return src, m.group(1)


class TestNguongTuan(unittest.TestCase):

    def test_hang_so_la_1(self):
        """`GROUP_MIN_SAMPLE` moi la thu `scoring.aggregate` doc de cham diem."""
        src = _read("constants.py")
        m = re.search(r"GROUP_MIN_SAMPLE\s*=\s*\{(.*?)\}", src, re.S)
        self.assertIsNotNone(m, "khong tim thay GROUP_MIN_SAMPLE")
        blk = m.group(1)
        w = re.search(r"GROUP_WEEKLY_REPORT:\s*(\d+)", blk)
        self.assertIsNotNone(w)
        self.assertEqual(w.group(1), "1",
                         "nguong nhom Bao cao tuan phai la 1")

    def test_cac_nhom_khac_khong_bi_ha_theo(self):
        """Ha nguong cua MOT nhom khong duoc keo theo bon nhom con lai."""
        src = _read("constants.py")
        blk = re.search(r"GROUP_MIN_SAMPLE\s*=\s*\{(.*?)\}", src, re.S).group(1)
        for key in ("GROUP_APPROVAL", "GROUP_ATTENDANCE", "GROUP_RSVP", "GROUP_TASK"):
            v = re.search(key + r":\s*(\d+)", blk)
            self.assertIsNotNone(v, "thieu %s" % key)
            self.assertEqual(v.group(1), "5", "%s phai giu nguyen 5" % key)

    def test_patch_doi_ca_ban_ghi_hien_thi(self):
        """Doi hang so ma quen ban ghi thi trang se noi mot dang, he thong cham
        mot dang khac."""
        src = _read("patches", "p012_weekly_min_sample.py")
        self.assertIn('TYPE_CODE = "WEEKLY_REPORT"', src)
        self.assertIn("NEW_MIN = 1", src)
        self.assertIn("min_sample", src)

    def test_patch_fail_safe(self):
        src = _read("patches", "p012_weekly_min_sample.py")
        body = src[src.index("def execute():"):]
        self.assertIn("except Exception:", body)
        self.assertNotIn("raise", body)


class TestBuocXuLy(unittest.TestCase):
    """Buoc xu ly chua duoc cham diem - trang phai noi ro dieu do."""

    def test_co_ham_nhan_dien(self):
        _, js = _page()
        self.assertIn("function isFulfillment(", js)

    def test_co_nhan_chua_tinh_vao_sla(self):
        _, js = _page()
        self.assertIn("chưa tính vào %SLA", js)

    def test_khong_go_cau_hinh_han(self):
        """Trang chi DAN NHAN. Neu mot ngay nao do co ai do sua tep nay thanh
        'gia vo buoc xu ly khong co han', bai kiem nay se do: con so gio do la
        han VAN HANH that, dang dieu khien nhac han trong Approval Center, va
        giau no di la giau mot thu dang chay."""
        _, js = _page()
        blk = js[js.index("function stepLine("):]
        blk = blk[:blk.index("\n  }")]
        self.assertIn("r.hours", blk, "van phai hien so gio that cua buoc xu ly")

    def test_giai_thich_dau_gach_ngang_o_bang_phong_ban(self):
        _, js = _page()
        self.assertIn("chưa đủ mẫu để ra tỉ lệ riêng", js)


if __name__ == "__main__":
    unittest.main()
