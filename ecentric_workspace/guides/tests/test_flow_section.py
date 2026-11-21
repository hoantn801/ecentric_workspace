# Copyright (c) 2026, eCentric and contributors
"""So do quy trinh theo vai tro trong bai huong dan (guides.flow_section).

Moi muc canh mot kieu hong:
  * so do co nut khong ung buoc (hoac buoc khong co nut) -> chon vai tro to sang sai cho;
  * buoc nhac vai tro khong khai -> chip vai tro thieu viec;
  * markup lech moc ma ec_iso_docs.js doc -> so do khong ve, khong ai bao;
  * chu Jinja lot vao Web Page -> trang hong luc render.
Chay doc lap, khong can frappe.
"""
import copy
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDES = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(GUIDES))
sys.path.insert(0, REPO)

from ecentric_workspace.guides import flow_section  # noqa: E402

PKG_PATH = os.path.join(GUIDES, "pages", "hop_dong", "quy_trinh.json")
ISO_JS = os.path.join(REPO, "ecentric_workspace", "public", "js", "ec_iso_docs.js")
ASSETS = ("https://cdn.test/mermaid.min.js", "/assets/ecentric_workspace/js/ec_iso_docs.js?v=t")


def _pkg():
    with io.open(PKG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class TestGoiHopDong(unittest.TestCase):
    def test_goi_hop_dong_khong_loi(self):
        self.assertEqual(flow_section.errors(_pkg()), [])

    def test_moi_vai_tro_deu_co_viec(self):
        html = flow_section.render(_pkg(), *ASSETS)
        for r in _pkg()["vai_tro"]:
            with self.subTest(vai_tro=r["ma"]):
                self.assertIn('data-r="%s"' % r["ma"], html)

    def test_ke_toan_to_sang_dung_cac_buoc(self):
        from ecentric_workspace.iso_docs import view
        kt = next(r for r in view.flow(_pkg())["roles"] if r["ma"] == "KT")
        self.assertEqual(kt["nodes"], ["S2", "S8", "S17", "S21", "S27", "S29", "S30"])

    def test_cap_nhat_24_11(self):
        """24/11: duyet 5 cap (Nhan su chi HD lao dong), nut tao ban ky PR-J, o CCCD/MST, BBNT duyet 3 cap."""
        from ecentric_workspace.iso_docs import view
        steps = {b["id"]: b for b in _pkg()["buoc"]}
        ns = next(r for r in view.flow(_pkg())["roles"] if r["ma"] == "NS")
        self.assertEqual(ns["nodes"], ["S10"])
        self.assertIn("lao động", steps["S10"]["ten"])
        self.assertIn("Xác nhận hợp đồng & tạo bản ký", steps["S4"]["dien_giai"])
        self.assertIn("CCCD / MST người ký phía đối tác", steps["S3"]["dien_giai"])
        self.assertIn("Kế toán tổng hợp → Kế toán trưởng → CEO", steps["S20"]["dien_giai"])
        self.assertIn("đã duyệt xong", steps["S25"]["dien_giai"])

    def test_form_erp_tro_dung_form(self):
        html = flow_section.render(_pkg(), *ASSETS)
        self.assertIn('href="/approvals/contract-review"', html)
        self.assertIn('href="/approvals/payment-request"', html)


class TestLuatKiem(unittest.TestCase):
    def test_nut_thua_hoac_thieu_bi_bat(self):
        p = _pkg()
        p["so_do_mermaid"] = p["so_do_mermaid"].replace('S30["30. Thanh lý hợp đồng"]', "")
        self.assertTrue(any("thieu nut" in e for e in flow_section.errors(p)))
        p = _pkg()
        p["so_do_mermaid"] += '\nS99["thua"]'
        self.assertTrue(any("khong ung voi buoc" in e for e in flow_section.errors(p)))

    def test_vai_tro_la_bi_bat(self):
        p = _pkg()
        p["buoc"][0]["A"] = "XX"
        self.assertTrue(any("XX" in e for e in flow_section.errors(p)))

    def test_tu_khoa_mermaid_cam_bi_bat(self):
        p = _pkg()
        p["so_do_mermaid"] += "\nclick S1 href \"javascript:alert(1)\""
        self.assertTrue(flow_section.errors(p))

    def test_goi_sai_thi_render_nem_loi(self):
        p = copy.deepcopy(_pkg())
        p["buoc"] = []
        with self.assertRaises(ValueError):
            flow_section.render(p, *ASSETS)

    def test_chu_jinja_khong_lot_vao_trang(self):
        p = _pkg()
        p["buoc"][0]["dien_giai"] = "xem {{ abc }}"
        with self.assertRaises(ValueError):
            flow_section.render(p, *ASSETS)


class TestKhopVoiBoVeIso(unittest.TestCase):
    """Trang nap chinh ec_iso_docs.js: moc ma JS do doc phai co du trong markup."""

    def test_markup_co_du_moc_js_doc(self):
        html = flow_section.render(_pkg(), *ASSETS)
        for mark in ("data-eti-flow", 'data-roles="', 'id="eti-flow"', 'id="eti-flow-msg"',
                     'id="eti-src"', 'id="eti-mine"', 'id="eti-mine-t"', 'id="eti-mine-list"',
                     'data-dir="TD"', 'data-dir="LR"', 'data-z="0"', 'class="eti-chip is-on"'):
            with self.subTest(mark=mark):
                self.assertIn(mark, html)

    def test_js_iso_van_doc_cac_moc_do(self):
        js = io.open(ISO_JS, encoding="utf-8").read()
        for mark in ("[data-eti-flow]", "'eti-flow'", "'eti-flow-msg'", "'eti-src'", "'eti-mine'",
                     "'eti-mine-t'", "'eti-mine-list'", ".eti-chip", "[data-dir]", "[data-z]"):
            with self.subTest(mark=mark):
                self.assertIn(mark, js, "ec_iso_docs.js doi moc %s - bai huong dan se mat so do" % mark)

    def test_script_mermaid_truoc_js_ve(self):
        html = flow_section.render(_pkg(), *ASSETS)
        self.assertLess(html.index(ASSETS[0]), html.index(ASSETS[1]))


if __name__ == "__main__":
    unittest.main()
