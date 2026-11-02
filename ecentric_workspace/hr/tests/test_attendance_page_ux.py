# Copyright (c) 2026, eCentric and contributors
"""UX trang /ec-hr/attendance (03/11/2026) - giu cac moc tren nguon fixture (main_section_html la
ban dang phuc vu; main_section kiem khi co moc). Hanh vi da chay thu bang Chromium voi API gia,
chup truoc/sau o 390px va 1366px.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_attendance_page_ux
"""
import io
import json
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIELDS = ("main_section", "main_section_html")


def _page():
    with io.open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("route") == "ec-hr/attendance"][0]


def _classify(h):
    i = h.index("  function classify(ds, maps, today){")
    return h[i:h.index("  function renderStats(", i)]


class AttendanceTruocNgayVaoLam(unittest.TestCase):
    """ec-att-doj-v1: ngay truoc ngay vao lam (server tra `doj`) khong to "Thieu"."""

    def test_lich_chinh_bo_qua_ngay_truoc_doj(self):
        for f in FIELDS:
            c = _classify(_page()[f])
            self.assertIn("ec-att-doj-v1", c, f)
            i = c.index("state.data.doj && ds < state.data.doj")
            # chan doj phai dung TRUOC moi nhanh tra ve 'missing'
            self.assertLess(i, c.index("cls:'missing'"), f)
            self.assertIn("cls:'future prejoin'", c, f)

    def test_lich_thanh_vien_bo_qua_ngay_truoc_doj(self):
        for f in FIELDS:
            h = _page()[f]
            self.assertIn('else if(ds<today&&!(m.doj&&ds<m.doj)){cls="c-miss"', h, f)
            self.assertNotIn('else if(ds<today){cls="c-miss"', h, f)

    def test_mau_ngay_ngoai_vp_trong_lich_thanh_vien(self):
        # truoc: dong "c-out{...}" mat tien to -> ngay lam viec ben ngoai khong co mau
        h = _page()["main_section_html"]
        self.assertIsNone(re.search(r"(?m)^c-out\{", h))
        self.assertIn("#ec-attm .c-out{", h)


if __name__ == "__main__":
    unittest.main()
