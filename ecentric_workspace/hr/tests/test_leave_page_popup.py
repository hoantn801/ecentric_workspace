# Copyright (c) 2026, eCentric and contributors
"""06/10/2026 (ec-lv-popup-v1): trang /ec-hr/leave.

Case sang.bui: bam "Duyet" o "Don cho ban duyet" thi popup chi tiet (chi de xem, khong
co nut) bat len cung luc -> nguoi duyet tuong chua duyet duoc; loi 403 thieu quyen lai
hien "Ban can dang nhap lai" -> F5 / dang xuat ma van ket.
Sua: bam nut trong dong KHONG mo popup; popup cua don dang cho minh duyet co nut
Duyet/Tu choi (bam ho nut cua dong, chung mot duong duyet cua dong); 403 chi bao
dang nhap lai khi het phien that.
Hanh vi da chay thu bang jsdom (bam nut dong, bam dong -> popup -> Duyet, 403
PermissionError, 403 SessionExpired). File nay giu cac moc tren nguon fixture.
"""
import io
import json
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _page():
    with io.open(os.path.join(APP, "fixtures", "web_page.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("route") == "ec-hr/leave"][0]


class LeavePagePopup(unittest.TestCase):
    def setUp(self):
        self.pg = _page()

    def test_ca_hai_ban_noi_dung_deu_sua(self):
        for k in ("main_section", "main_section_html"):
            self.assertGreaterEqual(self.pg[k].count("ec-lv-popup-v1"), 3, k)

    def test_bam_nut_trong_dong_khong_mo_popup(self):
        for k in ("main_section", "main_section_html"):
            src = self.pg[k]
            i = src.index('var row=ev.target.closest?ev.target.closest(".lv-row,.lv-trow")')
            j = src.index("var nm=await resolveName(row)", i)
            self.assertIn('if(ev.target.closest("button"))return;', src[i:j], k)

    def test_popup_co_nut_chi_khi_don_cho_minh_duyet(self):
        for k in ("main_section", "main_section_html"):
            src = self.pg[k]
            self.assertIn('curRow.closest("#lv-mgr")', src, k)
            self.assertIn('m.status==="Open"', src, k)
            # dung lai nut cua dong, khong goi API rieng
            self.assertIn('r.querySelector("button[data-act=\\""+a+"\\"]")', src, k)
            i = src.index("__ecLvDetailV1")
            self.assertNotIn("ec_hr_leave_decide", src[i:src.index("})();", i)], k)

    def test_403_chi_bao_dang_nhap_lai_khi_het_phien(self):
        for k in ("main_section", "main_section_html"):
            src = self.pg[k]
            self.assertNotIn("if(r.status===403) msg='Bạn cần đăng nhập lại.';", src, k)
            self.assertTrue(re.search(r"SessionExpired\|AuthenticationError", src), k)
            self.assertIn("Không đủ quyền thực hiện: ", src, k)


if __name__ == "__main__":
    unittest.main()
