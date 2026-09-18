# Copyright (c) 2026, eCentric and contributors
"""Kiem tra tinh cua trang /sla. KHONG import frappe.

Ba thu duoc khoa o day, moi thu deu tung hong that mot lan:

1. ES5. Trang nay chay trong Web Page cua Frappe, di qua bundler khac voi code
   Desk. Mot dau `=>` hay mot template literal lot vao la ca trang trang tron -
   khong phai mot khoi hong, ma TRANG TRON, vi script chet ngay dong dau.

2. Loc trang thai cua khoi "Dieu gi dang keo diem xuong". Tu ban nay, trang goi
   `person_items` voi `only_failed: 0` (khoi "Dang cho ban" can ca nhung dong
   con han). Neu ai do bo cai loc `Late`/`Missed` o duoi thi danh sach "keo diem
   xuong" se chua ca nhung viec CHUA TOI HAN - va so dong khong con khop voi con
   so backend in ngay canh no. Do la kieu hong khong bao gio bao loi: no chi lam
   nguoi ta dem tay ra mot con so khac roi khong tin bang diem nua.

3. Khong co phep tinh ti le trong JS. Be rong cac doan thanh thanh phan phai di
   ra tu `flex-grow` = so dem cua backend, khong phai tu mot phep chia phan tram.
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "pages", "scoreboard", "main_section.html")


def _src():
    with io.open(PAGE, encoding="utf-8") as fh:
        return fh.read()


def _script(src):
    m = re.search(r"<script id=\"ec-sla-scoreboard\">(.*?)</script>", src, re.S)
    assert m, "khong tim thay khoi script cua trang"
    return m.group(1)


def _code_only(js):
    """Bo dong comment `//` va chuoi, de khong bat nham tu khoa trong van ban."""
    out = []
    for line in js.split("\n"):
        s = line.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        out.append(line)
    return "\n".join(out)


class TestScoreboardPage(unittest.TestCase):

    def test_trang_ton_tai_va_co_script(self):
        src = _src()
        self.assertIn('id="ec-sla-root"', src)
        self.assertIn('data-ec-shell="1"', src)   # van dung shell dung chung
        self.assertTrue(len(_script(src)) > 5000)

    def test_khong_co_cu_phap_es6(self):
        js = _code_only(_script(_src()))
        for tok, why in [
            ("=>", "arrow function"),
            ("`", "template literal"),
            ("const ", "khai bao const"),
            ("let ", "khai bao let"),
            ("...", "spread"),
        ]:
            self.assertNotIn(tok, js, "tim thay %s (%s) - trang phai la ES5" % (tok, why))

    def test_goi_person_items_khong_loc_thi_phai_co_loc_o_duoi(self):
        js = _script(_src())
        if "only_failed: 0" in js:
            self.assertIn("'Late'", js,
                          "goi person_items khong loc ma khong thay loc Late/Missed")
            self.assertIn("'Missed'", js,
                          "goi person_items khong loc ma khong thay loc Late/Missed")

    def test_khoi_keo_diem_xuong_chi_nhan_late_va_missed(self):
        js = _script(_src())
        m = re.search(r"var failed = .*?;", js, re.S)
        self.assertIsNotNone(m, "khong tim thay bien `failed` cua khoi nguyen nhan")
        blk = m.group(0)
        self.assertIn("'Late'", blk)
        self.assertIn("'Missed'", blk)
        for bad in ("'Open'", "'Met'", "'Excluded'"):
            self.assertNotIn(bad, blk,
                             "%s khong duoc coi la mot dau viec dang keo diem xuong" % bad)

    def test_thanh_thanh_phan_dung_flex_grow_chu_khong_phai_phan_tram(self):
        js = _script(_src())
        m = re.search(r"function compBar\(.*?\n  \}", js, re.S)
        self.assertIsNotNone(m, "khong tim thay compBar")
        blk = m.group(0)
        self.assertIn("flex-grow:", blk)
        # Khong duoc co phep chia hay nhan trong ham nay: be rong la viec cua
        # trinh duyet, khong phai cua JS.
        self.assertNotIn("/ ", blk.replace("//", ""))
        self.assertNotIn("* 100", blk)
        self.assertNotIn("Math.round", blk)

    def test_nguong_mau_dung_mot_bo_voi_the_tren_trang_chu(self):
        """90 / 70 - giong `sla_home_card.js`. Hai nguong lech nhau se lam mot
        nguoi 72% thay hai mau khac nhau o hai trang cua cung mot he thong."""
        js = _script(_src())
        m = re.search(r"function rateClass\(v\)\{(.*?)\n  \}", js, re.S)
        self.assertIsNotNone(m, "khong tim thay rateClass")
        blk = m.group(1)
        self.assertIn("v >= 90", blk)
        self.assertIn("v >= 70", blk)

    def test_moi_ti_le_deu_di_kem_mau_so(self):
        """Khong duoc co mot noi nao in ti le tong ma khong in kem `scored`."""
        js = _script(_src())
        self.assertIn("đầu việc được chấm", js)
        self.assertIn("được tính điểm", js)

    def test_khong_dung_ky_tu_unicode_thay_cho_icon(self):
        """Icon phai la SVG ve tay, mot do day net.

        `→` KHONG nam trong danh sach: trong "16:00 → 18:00" no la dau noi cua
        mot khoang thoi gian, khong phai mot icon doi lot. Cam no o day se ep
        nguoi sau thay bang mot tu, va cau do doc dai hon ma khong ro hon.
        """
        src = _code_only(_src())
        for glyph in ("✓", "✔", "✗", "⚠", "★", "●", "▲", "►"):
            self.assertNotIn(glyph, src,
                             "dung %s thay cho icon - phai ve bang SVG" % glyph)

    def test_ton_trong_prefers_reduced_motion(self):
        self.assertIn("prefers-reduced-motion", _src())


if __name__ == "__main__":
    unittest.main()
