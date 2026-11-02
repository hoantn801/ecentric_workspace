# Copyright (c) 2026, eCentric and contributors
"""UX trang /ec-hr/leave (03/11/2026) - giu cac moc tren nguon fixture (CA main_section lan
main_section_html). Hanh vi da chay thu bang Chromium voi API gia, chup truoc/sau o 390px va 1366px.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_leave_page_ux
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
        return [r for r in json.load(fh) if r.get("route") == "ec-hr/leave"][0]


class LeaveOverlayVars(unittest.TestCase):
    """Form xin nghi, toast va popup chi tiet nam NGOAI #ec-hr-lv-root (markup dong root som) ->
    var(--green-b) ... khong xac dinh: toast trong suot, o Ly do mat vien, nut Duyet trong popup
    trong suot. Bien mau phai duoc khai bao cho chinh ba khoi do."""

    def test_bien_mau_cho_khoi_ngoai_root(self):
        for f in FIELDS:
            h = _page()[f]
            m = re.search(r"\.lv-modal-bg,#lv-toast,#ec-lvd-back\{([^}]*)\}", h)
            self.assertTrue(m, f)
            for v in ("--green-b", "--red-b", "--border", "--navy", "--gray-b", "--amber-b"):
                self.assertIn(v + ":", m.group(1), (f, v))
            self.assertIn(".lv-modal-bg *,#ec-lvd-back *{box-sizing:border-box}", h, f)



class LeaveDates(unittest.TestCase):
    """ec-lv-dates-v1: doi Tu ngay thi Den ngay di theo; chon nguoc ngay thi noi ro sai o dau."""

    def test_den_ngay_di_theo_tu_ngay(self):
        for f in FIELDS:
            h = _page()[f]
            self.assertIn("ec-lv-dates-v1", h, f)
            # listener cua lv-from gan TRUOC vong forEach gan calc -> calc doc Den ngay moi
            i = h.index("el('lv-from').addEventListener('change',function(){ var f=el('lv-from').value")
            self.assertLess(i, h.index("['lv-from','lv-to','lv-type','lv-halfday','lv-hdate'].forEach"), f)
            self.assertIn("el('lv-to').setAttribute('min',f)", h, f)

    def test_loi_ngay_noi_ro(self):
        for f in FIELDS:
            h = _page()[f]
            self.assertNotIn("Vui lòng chọn ngày hợp lệ", h, f)
            self.assertIn("Đến ngày đang trước Từ ngày", h, f)
            self.assertIn("Chọn Từ ngày và Đến ngày.", h, f)


class LeaveTiengViet(unittest.TestCase):
    """ec-lv-vi-v1: ten loai phep / trang thai tieng Viet o moi danh sach; dong co data-name."""

    def test_danh_sach_khong_ghep_ten_loai_tho(self):
        for f in FIELDS:
            h = _page()[f]
            self.assertIn("ec-lv-vi-v1", h, f)
            for raw in ("<b>'+a.type+'</b>", "· '+p.type+' ·", "<span>'+r.type+' ·", "'\">'+r.st+'</span>"):
                self.assertNotIn(raw, h, (f, raw))
            self.assertIn("'<div class=\"lv-row\" data-name=\"'+escH(a.name)+'\">", h, f)
            self.assertIn("'<div class=\"lv-trow\" data-name=\"'+escH(r.name)+'\">", h, f)
            self.assertIn("(window.ecLvTypeVi||String)(m.leave_type", h, f)
            # mot bang ten duy nhat cho ca form lan danh sach
            self.assertEqual(h.count("'Annual Leave':'Nghỉ phép năm'"), 1, f)

if __name__ == "__main__":
    unittest.main()
