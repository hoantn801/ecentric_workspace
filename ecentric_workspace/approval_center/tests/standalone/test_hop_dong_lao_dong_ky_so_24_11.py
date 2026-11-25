# Copyright (c) 2026, eCentric and contributors
"""Ky so hop dong lao dong (WF03) - yeu cau chat Ky so 24/11/2026 truoc khi bat ho so "Hop dong lao dong":
  * o "Ban PDF de ky" cho hop dong lao dong (tai PDF tay, hoac nut tu chuyen tu tep Word HR dinh kem);
  * hook ec_esign_signing_files tra [sign_pdf] cho hop dong lao dong (truoc tra rong -> chan khoa goi);
  * hop dong thuong khac van rong; verify giu not_applicable (khong doi o day);
  * trang: o nam tren khoi Ky so cua phieu lao dong, ghi ro moc [[KY_BEN_A]] / [[KY_BEN_B]].
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_lao_dong_ky_so_24_11
"""
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import STATE, Throw, _fresh  # noqa: E402
from test_hop_dong_ky_so_23_11 import P, _hooks, _kol_doc, _read  # noqa: E402

LABOR = "Labor / Hợp đồng lao động (EC)"


def _labor_doc(**kw):
    base = dict(contract_type=LABOR, contract_no=None, creator=None, request_type="New Contract",
                esign_flow="hd_lao_dong", request_attachment="/private/files/HDLD_A.docx",
                contract_file=None, sign_pdf=None)
    base.update(kw)
    d = _kol_doc(**base)
    d["db_set"] = lambda k, v: d.__setitem__(k, v)
    return d


class LaoDongBanPdf(unittest.TestCase):
    def _mod(self, enabled=True):
        _fresh("req@ec")
        self.calls = []
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: enabled

        def docx_to_pdf(doc, url):
            self.calls.append(("convert", url))
            return {"file_url": "/private/files/HDLD_A.pdf", "file_name": "HDLD_A.pdf"}
        gate.docx_to_pdf = docx_to_pdf
        sys.modules[P + "esign_gate"] = gate
        files = types.ModuleType(P + "kol_files")
        files.claim_upload = lambda doc, url, user: self.calls.append(("claim", url)) or url
        sys.modules[P + "kol_files"] = files
        sys.modules.pop(P + "kol_sign_pdf", None)
        m = importlib.import_module(P + "kol_sign_pdf")
        m._drop_old = lambda doc, url: None
        return m

    def test_tai_pdf_tay_khong_can_so_hop_dong(self):
        m = self._mod()
        d = _labor_doc()
        r = m.attach("CR-1", "/private/files/ban-ky.pdf", "req@ec")
        self.assertEqual(d["sign_pdf"], "/private/files/ban-ky.pdf")
        self.assertTrue(r["esign"])

    def test_pdf_hr_dinh_kem_dung_lam_ban_ky_duoc(self):
        m = self._mod()
        d = _labor_doc(request_attachment="/private/files/HDLD_A.pdf")
        m.attach("CR-1", "/private/files/HDLD_A.pdf", "req@ec")
        self.assertEqual(d["sign_pdf"], "/private/files/HDLD_A.pdf")
        self.assertFalse(m.is_stale(d))

    def test_nut_chuyen_tu_tep_word_hr(self):
        m = self._mod()
        d = _labor_doc()
        m.make_from_template("CR-1", "req@ec")
        self.assertEqual(self.calls, [("convert", "/private/files/HDLD_A.docx"), ("claim", "/private/files/HDLD_A.pdf")])
        self.assertEqual(d["sign_pdf"], "/private/files/HDLD_A.pdf")

    def test_tep_hr_la_pdf_thi_khong_co_nut(self):
        m = self._mod()
        d = _labor_doc(request_attachment="/private/files/HDLD_A.pdf")
        v = m.view(d, "req@ec")
        self.assertTrue(v["can_edit"])
        self.assertFalse(v["can_make"])
        self.assertEqual(v["kind"], "labor")
        with self.assertRaises(Throw) as cm:
            m.make_from_template("CR-1", "req@ec")
        self.assertIn(".docx", str(cm.exception))
        self.assertEqual(self.calls, [])

    def test_view_lao_dong(self):
        m = self._mod()
        d = _labor_doc()
        v = m.view(d, "req@ec")
        self.assertTrue(v["can_make"])
        self.assertFalse(m.view(d, "other@ec")["can_edit"])
        self.assertFalse(self._mod(enabled=False).view(_labor_doc(), "req@ec")["can_make"])

    def test_hop_dong_thuong_khong_co_o(self):
        m = self._mod()
        d = _labor_doc(contract_type="Purchase / Mua vào (EC)")
        self.assertIsNone(m.view(d, "req@ec"))
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/x.pdf", "req@ec")

    def test_kol_van_can_so_hop_dong(self):
        m = self._mod()
        _kol_doc(contract_no=None, contract_file=None)
        with self.assertRaises(Throw):
            m.attach("CR-1", "/private/files/x.pdf", "req@ec")


class LaoDongTepKy(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")
        sys.modules.pop(P + "kol_sign_pdf", None)
        sys.modules.pop(P + "esign_gate", None)

    def test_lao_dong_tra_ban_pdf_de_ky(self):
        _labor_doc(sign_pdf="/private/files/HDLD_A.pdf")
        self.assertEqual(_hooks().signing_files("CR-1"), ["/private/files/HDLD_A.pdf"])

    def test_lao_dong_chua_co_pdf_rong(self):
        _labor_doc(sign_pdf=None)
        self.assertEqual(_hooks().signing_files("CR-1"), [])

    def test_hop_dong_thuong_van_rong(self):
        _labor_doc(contract_type="Purchase / Mua vào (EC)", sign_pdf="/private/files/x.pdf")
        self.assertEqual(_hooks().signing_files("CR-1"), [])


class LaoDongTrang(unittest.TestCase):
    def setUp(self):
        self.page = _read("features/contract_review/ui/main_section.html")
        self.svc = _read("features/contract_review/application/kol_service.py")

    def test_o_nam_truoc_khoi_ky_so(self):
        self.assertIn('KOL.laborSignHTML(det)+esignSlotHTML(biz)', self.page)

    def test_huong_dan_moc_ky(self):
        i = self.page.index("laborSignPdfHTML:function")
        seg = self.page[i:i + 3000]
        self.assertIn("[[KY_BEN_A]]", seg)
        self.assertIn("[[KY_BEN_B]]", seg)
        self.assertIn("1pt", seg)
        self.assertIn('data-kol="makepdf"', seg)
        self.assertIn('data-kol="signpdf"', seg)

    def test_nut_doc_o_lao_dong(self):
        self.assertIn("spv=((ex.kol||{}).sign_pdf)||ex.sign_pdf||{}", self.page)

    def test_detail_extra_lao_dong(self):
        # 25/11: detail_extra boc them esign_wait; nhanh theo loai hop dong nam o _detail_extra.
        seg = self.svc[self.svc.index("def _detail_extra("):]
        self.assertIn("LABOR_CONTRACT_TYPE", seg[:900])
        self.assertIn('{"sign_pdf": kol_sign_pdf.view(', seg[:900])


if __name__ == "__main__":
    unittest.main()
