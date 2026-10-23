# Copyright (c) 2026, eCentric and contributors
"""23/10/2026 (ec-lv-songay-v1): so ngay nghi tren form /ec-hr/leave do SERVER tinh.

Case Linh: xin 12/11 -> 20/11, form hien "So ngay nghi: 9 - so du sau khi nghi: 0.5" vi JS
dem lich ca thu 7, chu nhat. HRMS (ham don se dung khi luu) tinh dung 7 ngay. Sua: form goi
hrms ... get_number_of_leave_days va chi hien thi ket qua.
Hanh vi da chay thu bang Chromium voi API gia (12->20/11 = 7, T7-CN = 0, nua ngay, chon
nguoc ngay, tra loi cu bi bo qua). File nay giu cac moc tren nguon fixture.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_leave_page_songay
"""
import io
import json
import os
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HRMS_FN = "hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days"


def _page():
    with io.open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("route") == "ec-hr/leave"][0]


def _calc(src):
    i = src.index("function calc(){")
    return src[i:src.index("function showCalc(", i)]


class LeavePageSoNgay(unittest.TestCase):
    def setUp(self):
        self.pg = _page()

    def test_ca_hai_ban_noi_dung_deu_sua(self):
        for k in ("main_section", "main_section_html"):
            self.assertIn("ec-lv-songay-v1", self.pg[k], k)

    def test_so_ngay_lay_tu_hrms_khong_tu_dem(self):
        for k in ("main_section", "main_section_html"):
            c = _calc(self.pg[k])
            self.assertIn(HRMS_FN, c, k)
            # days() chi con de biet khoang ngay hop le; con so hien ra phai la cua server.
            self.assertNotIn("ty.bal-n", c, k)
            self.assertIn("showCalc(lt, Number(v)||0)", c, k)

    def test_gui_du_tham_so_nua_ngay(self):
        for k in ("main_section", "main_section_html"):
            c = _calc(self.pg[k])
            for p in ("employee:", "leave_type:lt", "from_date:", "to_date:", "half_day:",
                      "half_day_date:"):
                self.assertIn(p, c, (k, p))

    def test_tra_loi_cu_khong_de_len_tra_loi_moi(self):
        for k in ("main_section", "main_section_html"):
            c = _calc(self.pg[k])
            self.assertIn("var seq=++ecCalcSeq;", c, k)
            self.assertEqual(c.count("seq===ecCalcSeq"), 2, k)

    def test_doi_ngay_nua_ngay_cung_tinh_lai(self):
        for k in ("main_section", "main_section_html"):
            self.assertIn("['lv-from','lv-to','lv-type','lv-halfday','lv-hdate']", self.pg[k], k)

    def test_khoang_toan_ngay_nghi_bao_ro(self):
        for k in ("main_section", "main_section_html"):
            self.assertIn("không cần xin phép", self.pg[k], k)


if __name__ == "__main__":
    unittest.main()
