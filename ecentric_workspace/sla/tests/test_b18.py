# Copyright (c) 2026, eCentric and contributors
"""Lo B18 - o chon ky tren trang /sla. KHONG import frappe.

Bon thu duoc khoa o day. Ca bon deu la cach tinh nang nay hong ma trang van
trong binh thuong - kieu hong dat nhat, vi khong ai di bao loi:

1. PHAI THREAD `period` VAO CA BON CHO GOI API. Bo sot mot cho thi trang tron
   hai thang: bang diem thang 9 nam canh danh sach dau viec thang 10, va khong
   co gi tren man hinh noi cho nguoi doc biet.

2. DANH SACH KY PHAI LIEN TUC. Chi liet ke nhung thang co du lieu se tao ra lo
   hong ("12, 11, 09") ma nguoi doc khong the giai thich.

3. THANG HIEN TAI PHAI LUON CO. Sang ngay 1 moi thang chua ai phat sinh dau
   viec nao - va dung luc do o chon khong duoc rong.

4. DOI KY PHAI XOA CO NAP CUA TAB "Cach tinh SLA". Doan giai thich thang 9 chi
   dung cho thang 9; giu nguyen khi xem thang 10 la mot cau sai nam ngay tren
   trang giai thich cach cham diem.
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


class TestPeriodsBackend(unittest.TestCase):

    def setUp(self):
        self.src = _read("application", "scoreboard_service.py")

    def test_co_ham_periods(self):
        self.assertIsNotNone(_fn(self.src, "periods"))

    def test_khong_nem_loi(self):
        blk = self.src[self.src.index("def periods("):]
        self.assertIn("except Exception:", blk)
        self.assertNotIn("raise", blk)

    def test_api_scope_tra_ve_periods(self):
        api = _read("controllers", "api.py")
        self.assertIn("scoreboard_service.periods()", api)

    def test_khong_mo_endpoint_thua(self):
        """`scope` da duoc goi luc khoi dong; them mot endpoint nua la mot vong
        goi mang thua tren moi lan mo trang."""
        api = _read("controllers", "api.py")
        self.assertIsNone(_fn(api, "periods"))


class TestLuiThangThuanTuy(unittest.TestCase):
    """Phep lui mot thang chay tach roi, khong can frappe."""

    def _load(self):
        src = _read("application", "scoreboard_service.py")
        blk = src[src.index("def _prev_period("):]
        blk = blk[:blk.index("\ndef ")]
        ns = {}
        exec(compile(blk, "scoreboard_service", "exec"), ns)
        return ns["_prev_period"]

    def test_lui_trong_nam(self):
        f = self._load()
        self.assertEqual(f("2026-10"), "2026-09")

    def test_lui_qua_nam(self):
        f = self._load()
        self.assertEqual(f("2026-01"), "2025-12")

    def test_giu_hai_chu_so(self):
        f = self._load()
        self.assertEqual(f("2026-11"), "2026-10")
        self.assertEqual(f("2026-02"), "2026-01")


class TestTrangSla(unittest.TestCase):

    def setUp(self):
        self.html = _read("pages", "scoreboard", "main_section.html")

    def test_bon_cho_goi_api_deu_mang_period(self):
        for call in ("call('my_board', { period: S.period })",
                     "call('person_items', { period: S.period, only_failed: 0 })",
                     "call('department_board', { period: S.period })",
                     "call('person_board', { user: user, period: S.period })"):
            self.assertIn(call, self.html, "thieu period o: %s" % call)

    def test_khong_con_cho_goi_khong_period(self):
        """Mot cho sot lai se im lang tra ve thang hien tai."""
        for bad in ("call('my_board', {})",
                    "call('person_items', { only_failed: 0 })",
                    "call('department_board', {})",
                    "call('person_board', { user: user })"):
            self.assertNotIn(bad, self.html, "con cho khong mang period: %s" % bad)

    def test_doi_ky_nap_lai_tab_cach_tinh(self):
        blk = self.html[self.html.index("function setPeriod("):]
        blk = blk[:blk.index("\n  function ")]
        self.assertIn("S.loaded.rules = false", blk)
        self.assertIn("S.loaded.me = false", blk)
        self.assertIn("S.loaded.dept = false", blk)

    def test_danh_dau_thang_dang_dien_ra(self):
        self.assertIn("đang diễn ra", self.html)

    def test_co_duong_lui_khi_backend_cu(self):
        """Backend chua co `periods` thi o chon van phai dung duoc."""
        self.assertIn("(s.period ? [s.period] : [])", self.html)

    def test_es5_trong_doan_moi(self):
        """Trang nay chay tren trinh duyet cu cua may van phong - khong arrow,
        khong template literal, khong const/let."""
        i = self.html.index("function renderPeriodSel()")
        blk = self.html[i:self.html.index("function selectTab(")]
        self.assertNotIn("=>", blk)
        self.assertNotIn("`", blk)
        for kw in ("const ", "let "):
            self.assertNotIn(kw, blk)

    def test_mui_ten_duoc_ve_khong_phai_ky_tu(self):
        self.assertIn('class="sla-period-ic"', self.html)
        self.assertIn('<path d="m7 10 5 5 5-5"/>', self.html)

    def test_baseline_sha_khop_html(self):
        """Sua HTML ma quen bump baseline thi ban song giu nguyen trang cu."""
        import hashlib
        sha = hashlib.sha256(self.html.encode("utf-8")).hexdigest()
        ps = _read("pages", "scoreboard", "page_sync.py")
        self.assertIn('BASELINE_SHA256 = "%s"' % sha, ps,
                      "BASELINE_SHA256 khong khop sha cua main_section.html")


if __name__ == "__main__":
    unittest.main()
