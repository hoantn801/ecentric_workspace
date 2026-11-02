# Copyright (c) 2026, eCentric and contributors
"""Trang /ec-hr/attendance va /ec-hr/leave: chu do NGUOI DUNG go (ly do giai trinh, ly do di
muon, ly do nghi, ten) phai escape truoc khi ghep vao innerHTML.

Case (03/11/2026): nhan vien gui giai trinh / don nghi voi ly do `<img src=x onerror=...>` ->
doan JS chay trong trinh duyet quan ly / HR luc ho mo danh sach cho duyet (stored XSS, chay
bang phien cua nguoi co quyen cao hon). Kem theo: openDetail cua trang cham cong goi esc()
nhung ham chi khai bao trong IIFE "xem lich nhom" -> ReferenceError, bam vao ngay lam viec
ben ngoai da duyet thi khong mo duoc chi tiet.
Kiem tren nguon fixtures/web_page.json (CA main_section lan main_section_html) - KHONG can bench.
python -m unittest ecentric_workspace.hr.tests.test_hr_pages_escape"""
import io
import json
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIELDS = ("main_section", "main_section_html")


def _page(route):
    with io.open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        return [p for p in json.load(fh) if p.get("route") == route][0]


def _first_iife(html):
    """Script chinh cua trang = IIFE dau tien co 'use strict' (toi dong '})();' dau tien)."""
    for sc in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        if "'use strict'" in sc and ("function el(" in sc or "function getCsrf(" in sc):
            i = sc.index("(function(){")
            return sc[i:sc.index("\n})();", i)]
    raise AssertionError("khong thay script chinh")


RAW = re.compile(r"""\+\s*\(?\s*(p\.note|p\.reason|a\.note|p\.emp_name|r\.emp_name|maps\.appealNote\[ds\])""")


class TestEscape(unittest.TestCase):
    def _check(self, route, helper):
        page = _page(route)
        for f in FIELDS:
            main = _first_iife(page[f])
            self.assertIn("function %s(" % helper, main, "%s %s: thieu ham escape trong IIFE chinh" % (route, f))
            raw = RAW.findall(main)
            self.assertEqual(raw, [], "%s %s: ghep tho vao HTML: %s" % (route, f, raw))

    def test_cham_cong(self):
        self._check("ec-hr/attendance", "esc")

    def test_nghi_phep(self):
        self._check("ec-hr/leave", "escH")

    def test_esc_cua_openDetail_co_trong_cung_scope(self):
        main = _first_iife(_page("ec-hr/attendance")["main_section_html"])
        if "esc(owd" in main:
            self.assertIn("function esc(", main)


if __name__ == "__main__":
    unittest.main()
