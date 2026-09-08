# Copyright (c) 2026, eCentric and contributors
"""Hop dong cua module huong dan.

Cai bo test nay canh, noi cho gon: MOT bai huong dan duoc khai o registry phai
that su den duoc tay nguoi dung - co trang, co route dung, co anh, co duong ve.
Moi muc duoi day tuong ung mot kieu hong DA hoac SAP xay ra:

  * registry khai mot bai nhung khong ai lam trang -> the o Approval Center bam
    vao ra 404. Khong test thi khong ai biet cho toi luc nguoi dung bam.
  * route o registry va ROUTE o page_sync lech nhau mot dau gach -> y het tren.
  * bai tham chieu mot anh khong co trong repo -> trang len song voi o anh vo.
  * bai khong co duong ve -> dung y Hoan 08/09: "gan len thi nho co nut back ve
    nhe, chu khong no bi bo vo do".

Chay doc lap (khong can frappe): page_sync.py co `import frappe` nen o day KHONG
import no - doc bang AST. Doi lai, test chay duoc o may nao cung duoc.
"""
import ast
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDES = os.path.dirname(HERE)                       # .../ecentric_workspace/guides
APP = os.path.dirname(GUIDES)                        # .../ecentric_workspace
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.guides import page_sync_util  # noqa: E402
from ecentric_workspace.guides import registry        # noqa: E402

PAGES_DIR = os.path.join(GUIDES, "pages")


def _page_dir_of(slug):
    """Thu muc trang cua mot slug: dau gach ngang -> gach duoi (quy uoc goi Python)."""
    return os.path.join(PAGES_DIR, slug.replace("-", "_"))


def _module_const(path, name):
    """Doc mot hang so cap module bang AST - khong import (page_sync can frappe)."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return node.value.value
    return None


class TestRegistry(unittest.TestCase):
    def test_co_it_nhat_mot_bai(self):
        self.assertTrue(registry.GUIDES, "registry rong - phep kiem duoi dang mu")

    def test_moi_bai_khai_du_truong(self):
        for slug, g in registry.GUIDES.items():
            with self.subTest(slug=slug):
                for f in ("title", "short", "summary", "approval_types", "updated"):
                    self.assertTrue(g.get(f), "bai %s thieu truong %s" % (slug, f))
                self.assertIsInstance(g["approval_types"], list)

    def test_route_suy_ra_tu_slug(self):
        self.assertEqual(registry.route_of("abc"), "/huong-dan/abc")

    def test_tra_bai_theo_loai_yeu_cau(self):
        for code in ("PURCHASE_REQUEST", "PAYMENT_REQUEST"):
            with self.subTest(code=code):
                g = registry.guide_for_approval_type(code)
                self.assertIsNotNone(g, "%s phai co bai huong dan" % code)
                self.assertEqual(g["route"], "/huong-dan/dnmh-dntt")

    def test_loai_khong_co_bai_tra_None(self):
        self.assertIsNone(registry.guide_for_approval_type("LEAVE"))
        self.assertIsNone(registry.guide_for_approval_type(None))
        self.assertIsNone(registry.guide_for_approval_type(""))

    def test_khong_hai_bai_cung_gianh_mot_loai_yeu_cau(self):
        """Hai bai cung khai PAYMENT_REQUEST thi icon "?" tro toi bai nao la do
        thu tu dict - tuc la do may rui. Chan tu day."""
        seen = {}
        for slug, g in registry.GUIDES.items():
            for code in g.get("approval_types", ()):
                self.assertNotIn(code, seen,
                                 "%s duoc ca %s va %s nhan" % (code, seen.get(code), slug))
                seen[code] = slug


class TestMoiBaiDeuCoTrangThAT(unittest.TestCase):
    def test_co_thu_muc_va_hai_tep(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                d = _page_dir_of(slug)
                self.assertTrue(os.path.isdir(d), "thieu thu muc trang cho bai %s: %s" % (slug, d))
                for f in ("page_sync.py", "main_section.html"):
                    self.assertTrue(os.path.isfile(os.path.join(d, f)),
                                    "bai %s thieu %s" % (slug, f))

    def test_route_cua_trang_khop_registry(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                route = _module_const(os.path.join(_page_dir_of(slug), "page_sync.py"), "ROUTE")
                self.assertEqual("/" + (route or ""), registry.route_of(slug),
                                 "ROUTE o page_sync lech voi registry -> the bam ra 404")

    def test_trang_muc_luc_dung_route_goc(self):
        route = _module_const(os.path.join(PAGES_DIR, "index", "page_sync.py"), "ROUTE")
        self.assertEqual("/" + (route or ""), registry.ROUTE_PREFIX)

    def test_page_sync_ghi_ro_ten_template(self):
        """Ban ke ma bam (test_html_change_needs_resync) doc AST cua page_sync de
        tim template. Khong co chuoi ".html" o do thi trang huong dan nam ngoai
        tam kiem - sua HTML ma khong ai doi hoi patch resync."""
        for d in [os.path.join(PAGES_DIR, "index")] + \
                 [_page_dir_of(s) for s in registry.GUIDES]:
            with self.subTest(page=os.path.basename(d)):
                src = io.open(os.path.join(d, "page_sync.py"), encoding="utf-8").read()
                self.assertIn('"main_section.html"', src)


class TestNoiDungTrang(unittest.TestCase):
    def _html(self, d):
        return io.open(os.path.join(d, "main_section.html"), encoding="utf-8").read()

    def test_moi_anh_tham_chieu_deu_co_tep(self):
        for slug in registry.GUIDES:
            d = _page_dir_of(slug)
            html = self._html(d)
            names = re.findall(r"\{\{img:([^}]+)\}\}", html)
            with self.subTest(slug=slug):
                self.assertTrue(names, "bai %s khong nhung anh nao - co dung y khong?" % slug)
                for n in names:
                    self.assertTrue(os.path.isfile(os.path.join(d, "img", n.strip())),
                                    "bai %s thieu anh %s" % (slug, n))

    def test_thieu_anh_thi_NEM_LOI_chu_khong_de_o_vo(self):
        with self.assertRaises(ValueError):
            page_sync_util.embed_images("{{img:khong-co-that.jpg}}", os.path.join(GUIDES, "pages"))

    def test_duoi_anh_la_khong_ho_tro_cung_nem_loi(self):
        with self.assertRaises(ValueError):
            page_sync_util.embed_images("{{img:x.bmp}}", os.path.join(GUIDES, "pages"))

    def test_moi_bai_co_duong_ve(self):
        """Y Hoan 08/09: bai huong dan khong duoc "bo vo"."""
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                html = self._html(_page_dir_of(slug))
                self.assertIn('href="%s"' % registry.ROUTE_PREFIX, html,
                              "bai %s khong co duong ve muc luc" % slug)

    def test_muc_luc_liet_ke_du_moi_bai(self):
        listed = page_sync_util.render_guides_list()
        for slug, g in registry.GUIDES.items():
            with self.subTest(slug=slug):
                self.assertIn('href="%s"' % registry.route_of(slug), listed)
                self.assertIn(g["title"], listed)

    def test_muc_luc_rong_thi_noi_that(self):
        real = registry.GUIDES
        try:
            registry.GUIDES = {}
            self.assertIn("Chưa có hướng dẫn nào", page_sync_util.render_guides_list())
        finally:
            registry.GUIDES = real

    def test_dung_duoc_ca_trang_muc_luc(self):
        """build() that su chay: thay {{guides_list}} va nhung anh (base64)."""
        html = page_sync_util.build(os.path.join(PAGES_DIR, "index"), "main_section.html")
        self.assertNotIn("{{guides_list}}", html)
        self.assertIn('class="gcards"', html)

    def test_dung_duoc_moi_bai_va_anh_thanh_data_uri(self):
        for slug in registry.GUIDES:
            with self.subTest(slug=slug):
                html = page_sync_util.build(_page_dir_of(slug), "main_section.html")
                self.assertNotIn("{{img:", html)
                self.assertIn("data:image/", html)


if __name__ == "__main__":
    unittest.main()
