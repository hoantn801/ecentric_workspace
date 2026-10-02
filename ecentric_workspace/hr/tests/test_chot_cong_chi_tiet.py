# Copyright (c) 2026, eCentric and contributors
"""02/10/2026: khung chot cong - tong ket cong tung nguoi (cong / phep / khong luong / thieu) va
bam ten mo lich cong (ec-tsclose-detail-v1, ec-att-sum-leave-v1). KHONG can bench."""
import datetime as dt
import io
import json
import os
import re
import types
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _fixture(name):
    with io.open(os.path.join(APP, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def _leave_block():
    s = {r["name"]: r["script"] for r in _fixture("server_script.json")}["ec_hr_attendance_data"]
    i = s.index("# ec-att-sum-leave-v1")
    j = s.index("summary['lwp'] = sum_lwp", i) + len("summary['lwp'] = sum_lwp")
    return s[i:j]


def _run(leaves, atts, hol=(), doj=""):
    def add_days(d, n):
        return str(dt.date.fromisoformat(d) + dt.timedelta(days=n))
    fr = types.SimpleNamespace(
        db=types.SimpleNamespace(sql=lambda q, *a: [("Leave Without Pay",)]),
        utils=types.SimpleNamespace(add_days=add_days))
    g = {"frappe": fr, "leaves": leaves, "start": "2026-09-01", "end": "2026-09-30",
         "hol_by_day": {d: 1 for d in hol}, "att_by_day": atts, "doj": doj, "summary": {}}
    exec(_leave_block(), g)
    return g["summary"]


class TongKetNghi(unittest.TestCase):
    def test_phep_va_khong_luong_tach_rieng(self):
        s = _run([{"f": "2026-09-03", "t": "2026-09-04", "type": "Annual Leave"},
                  {"f": "2026-09-10", "t": "2026-09-10", "type": "Leave Without Pay"}], {})
        self.assertEqual((s["leave"], s["lwp"]), (2, 1))

    def test_bo_cuoi_tuan_le_va_ngoai_thang(self):
        s = _run([{"f": "2026-08-31", "t": "2026-09-07", "type": "Annual Leave"}], {},
                 hol=("2026-09-02", "2026-09-05", "2026-09-06"))
        # 01, 03, 04, 07 (02 le, 05-06 cuoi tuan, 31/08 ngoai thang)
        self.assertEqual(s["leave"], 4)

    def test_nua_ngay_va_ngay_di_lam(self):
        s = _run([{"f": "2026-09-08", "t": "2026-09-09", "type": "Annual Leave"}],
                 {"2026-09-08": {"s": "Half Day"}, "2026-09-09": {"s": "Present"}})
        self.assertEqual(s["leave"], 0.5)

    def test_truoc_ngay_vao_lam_khong_tinh(self):
        s = _run([{"f": "2026-09-01", "t": "2026-09-03", "type": "Annual Leave"}], {}, doj="2026-09-03")
        self.assertEqual(s["leave"], 1)


class KhungChotCong(unittest.TestCase):
    def setUp(self):
        self.h = [r for r in _fixture("web_page.json") if r.get("route") == "ec-hr/attendance"][0]["main_section_html"]

    def test_khong_them_khoi_script_style_co_id(self):
        ids = re.findall(r'<(?:script|style)[^>]*\bid="([^"]+)"', self.h)
        self.assertEqual(ids, [])

    def test_ten_bam_duoc_va_mo_dung_thang_dang_chot(self):
        self.assertIn("ec-tsclose-detail-v1", self.h)
        self.assertIn('data-emp="\' + tsEsc(m.employee)', self.h)
        self.assertIn("window.ecAttOpenMember(nb.getAttribute('data-emp'), nb.getAttribute('data-nm'), TS_PERIOD)", self.h)
        self.assertIn("window.ecAttOpenMember=function(emp,name,month)", self.h)

    def test_tong_ket_lay_tu_cung_nguon_voi_lich_cong(self):
        self.assertIn("api('ec_hr_attendance_data', { member: m.employee, month: TS_PERIOD })", self.h)
        for k in ("s.present", "s.working_total", "s.leave", "s.lwp", "s.missing"):
            self.assertIn(k, self.h)


if __name__ == "__main__":
    unittest.main()
