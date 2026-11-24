# Copyright (c) 2026, eCentric and contributors
"""PR-J (24/11/2026) - nut "Xac nhan hop dong & tao ban ky" tren form 27, theo ban giao chat Ky so:
  * server: kol_make_sign_pdf = .docx sinh tu MAU EC -> nen tang chuyen PDF -> gan lam Ban PDF de ky, CUNG
    request; mau doi tac / chua sinh .docx / chua ky so -> bao ro, khong goi nen tang;
  * loi cua nen tang (vd "Chua cau hinh thu vien tam de chuyen PDF") di nguyen ra nguoi dung;
  * view: can_make chi khi sua duoc + ky so + mau EC + da co .docx;
  * trang: nut goi kol_make_sign_pdf roi kol_auto_place_sign (request rieng), loi hien nguyen cau.
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_tao_ban_ky_24_11
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
from test_hop_dong_ky_so_23_11 import P, _kol_doc, _read  # noqa: E402

PARTNER = "Template from partner / Mẫu theo khung đối tác"
NO_LIB = "Chưa cấu hình thư viện tạm để chuyển PDF"


class TaoBanKyServer(unittest.TestCase):
    def _mod(self, enabled=True, convert=None):
        _fresh("req@ec")
        self.calls = []
        gate = types.ModuleType(P + "esign_gate")
        gate.enabled = lambda name: enabled

        def docx_to_pdf(doc, url):
            self.calls.append(("convert", url))
            if convert:
                return convert(doc, url)
            return {"file_url": "/private/files/hd.pdf", "file_name": "hd.pdf"}
        gate.docx_to_pdf = docx_to_pdf
        sys.modules[P + "esign_gate"] = gate
        files = types.ModuleType(P + "kol_files")
        files.claim_upload = lambda doc, url, user: self.calls.append(("claim", url)) or url
        sys.modules[P + "kol_files"] = files
        sys.modules.pop(P + "kol_sign_pdf", None)
        m = importlib.import_module(P + "kol_sign_pdf")
        m._drop_old = lambda doc, url: None
        return m

    def _doc(self, **kw):
        kw.setdefault("contract_file", "/private/files/hd.docx")
        d = _kol_doc(**kw)
        d["db_set"] = lambda k, v: d.__setitem__(k, v)
        return d

    def test_chuyen_roi_gan_lam_ban_ky(self):
        m = self._mod()
        d = self._doc()
        r = m.make_from_template("CR-1", "req@ec")
        self.assertEqual(self.calls, [("convert", "/private/files/hd.docx"), ("claim", "/private/files/hd.pdf")])
        self.assertEqual(d["sign_pdf"], "/private/files/hd.pdf")
        self.assertTrue(r["esign"])

    def test_mau_doi_tac_khong_chuyen(self):
        m = self._mod()
        self._doc(request_type=PARTNER)
        with self.assertRaises(Throw) as cm:
            m.make_from_template("CR-1", "req@ec")
        self.assertIn("mẫu của đối tác", str(cm.exception))
        self.assertEqual(self.calls, [])

    def test_chua_tao_hop_dong(self):
        m = self._mod()
        self._doc(contract_file=None)
        with self.assertRaises(Throw):
            m.make_from_template("CR-1", "req@ec")
        self.assertEqual(self.calls, [])

    def test_chua_ky_so_khong_goi_nen_tang(self):
        m = self._mod(enabled=False)
        self._doc()
        with self.assertRaises(Throw):
            m.make_from_template("CR-1", "req@ec")
        self.assertEqual(self.calls, [])

    def test_nguoi_khac_khong_tao(self):
        m = self._mod()
        self._doc()
        STATE["user"] = "other@ec"
        with self.assertRaises(Throw):
            m.make_from_template("CR-1", "other@ec")
        self.assertEqual(self.calls, [])

    def test_loi_nen_tang_di_nguyen_va_khong_gan(self):
        def boom(doc, url):
            raise Throw(NO_LIB)
        m = self._mod(convert=boom)
        d = self._doc()
        with self.assertRaises(Throw) as cm:
            m.make_from_template("CR-1", "req@ec")
        self.assertEqual(str(cm.exception), NO_LIB)
        self.assertNotEqual(d.get("sign_pdf"), "/private/files/hd.pdf")
        self.assertNotIn("claim", [c[0] for c in self.calls])

    def test_view_can_make(self):
        m = self._mod()
        d = self._doc()
        self.assertTrue(m.view(d, "req@ec")["can_make"])
        self.assertFalse(m.view(d, "other@ec")["can_make"])
        d["request_type"] = PARTNER
        self.assertFalse(m.view(d, "req@ec")["can_make"])
        d["request_type"] = "Template from EC / Mẫu theo khung EC"
        d["contract_file"] = None
        self.assertFalse(m.view(d, "req@ec")["can_make"])
        m2 = self._mod(enabled=False)
        d2 = self._doc()
        self.assertFalse(m2.view(d2, "req@ec")["can_make"])


class TaoBanKyGate(unittest.TestCase):
    def test_gate_goi_api_dung_chung_cua_nen_tang(self):
        src = _read("features/contract_review/application/esign_gate.py")
        seg = src[src.index("def docx_to_pdf("):]
        self.assertIn("platform.esign import api", seg)
        self.assertIn("convert_business_docx_to_pdf(CR_DT, doc.name, file_url)", seg)

    def test_api_mo_va_che_url(self):
        src = _read("features/contract_review/controllers/kol_api.py")
        seg = src[src.index("def kol_make_sign_pdf("):]
        self.assertIn('make_from_template(name, _me()), "sign_pdf")', seg[:400])
        self.assertIn('"kol_make_sign_pdf"', src[:src.index("def ")])
        self.assertIn("kol_make_sign_pdf", _read("features/contract_review/controllers/api.py"))


class TaoBanKyTrang(unittest.TestCase):
    def setUp(self):
        self.page = _read("features/contract_review/ui/main_section.html")

    def test_nut_chi_hien_khi_can_make(self):
        i = self.page.index('data-kol="makepdf"')
        self.assertIn("sp.can_make?", self.page[i - 200:i])
        self.assertIn("Xác nhận hợp đồng &amp; tạo bản ký", self.page)

    def test_thu_tu_va_loi_hien_nguyen(self):
        i = self.page.index('if(a==="makepdf") return call("kol_make_sign_pdf"')
        seg = self.page[i:i + 500]
        self.assertIn(".then(placeAfter)", seg)
        self.assertIn("extractServerMsg(e)", seg)
        self.assertNotIn("mapErr", seg)
        self.assertIn('call("kol_auto_place_sign"', self.page[self.page.index("var placeAfter="):i])

    def test_khong_jinja(self):
        i = self.page.index("var placeAfter=")
        self.assertNotIn("{{", self.page[i - 3000:i + 3000])


if __name__ == "__main__":
    unittest.main()
