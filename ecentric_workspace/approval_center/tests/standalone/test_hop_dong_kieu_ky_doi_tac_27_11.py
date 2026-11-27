# Copyright (c) 2026, eCentric and contributors
"""PO 27/11/2026: KOL hay chi ky anh -> phieu hop dong cho chon "Kieu ky cua doi tac" tren cong
(Ky anh / USB Token / eSign / VNeID / eKYC; trong = mac dinh cua cong).

  * external_handlers gui `sign_type` khi phieu chon; trong / gia tri la -> KHONG gui (nen tang dat
    mac dinh), khong bao gio gui ma cong khong nhan.
  * Luu / gui phieu: gia tri la bi xoa (clean_partner_sign_type).
  * Truong DocType + o chon tren trang + p582 resync, ban ke sha256.
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hop_dong_kieu_ky_doi_tac_27_11.py
"""
import hashlib
import importlib
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                    # cong push chay `python -m unittest <module>`
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Doc, _fresh  # noqa: E402

APP = os.path.abspath(os.path.join(HERE, "..", "..", ".."))   # goi ecentric_workspace
P = "ecentric_workspace.approval_center.features.contract_review."
KOL_TYPE = "KOL/KOC / Creator (EC)"
# Ma cong CMC nhan (nen tang ky so, providers/scts.PARTNER_SIGN_TYPES) - doc tu nguon, khong import.
_CONG = ("image", "token", "ekyc", "esign", "vnetid", "nfc")


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


def _doc(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type=KOL_TYPE, esign_flow="kol_wf09", creator="SUP-1",
            partner_signer_name="Nguyen Van A", partner_signer_email="giamdoc@cty.vn",
            partner_signer_phone="0909", requested_by="req@ec", owner="req@ec",
            partner_signer_identity=None, partner_sign_type=None)
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    return d


def _creator():
    row = {"ec_cr_type": "Công ty", "supplier_name": "Cty A", "ec_cr_email": "a@gmail.com",
           "ec_cr_cccd": None, "tax_id": "0312345678"}
    STATE["values"][("Supplier", "SUP-1")] = lambda field, as_dict: dict(row)


class KieuKy(unittest.TestCase):
    def setUp(self):
        _fresh("req@ec")
        _creator()
        self.hooks = importlib.import_module(P + "application.esign_hooks")
        self.flow = importlib.import_module(P + "domain.esign_flow")

    def test_chon_ky_anh_thi_gui_sign_type(self):
        _doc(partner_sign_type="image")
        rows = self.hooks.external_handlers("CR-1")
        self.assertEqual(rows[0]["sign_type"], "image")
        self.assertEqual(rows[0]["identity"], "0312345678")

    def test_de_trong_hoac_la_thi_khong_gui(self):
        for v in (None, "", "  ", "ky-anh", "nfc"):
            _doc(partner_sign_type=v)
            self.assertNotIn("sign_type", self.hooks.external_handlers("CR-1")[0], v)

    def test_moi_lua_chon_deu_la_ma_cong_nhan(self):
        self.assertEqual(set(self.flow.PARTNER_SIGN_TYPES), {"image", "token", "esign", "vnetid", "ekyc"})
        self.assertTrue(set(self.flow.PARTNER_SIGN_TYPES) <= set(_CONG))
        src = _read("platform/esign/providers/scts.py")
        cong = re.search(r"PARTNER_SIGN_TYPES = \(([^)]*)\)", src).group(1)
        for code in self.flow.PARTNER_SIGN_TYPES:
            self.assertIn('"%s"' % code, cong)

    def test_luu_phieu_xoa_gia_tri_la(self):
        d = _doc(partner_sign_type="ky-anh")
        self.flow.clean_partner_sign_type(d)
        self.assertIsNone(d.partner_sign_type)
        d = _doc(partner_sign_type=" token ")
        self.flow.clean_partner_sign_type(d)
        self.assertEqual(d.partner_sign_type, "token")

    def test_luu_va_gui_deu_goi_clean(self):
        for rel in ("application/kol_service.py", "application/service.py"):
            src = _read("approval_center/features/contract_review/" + rel)
            self.assertIn("esign_flow.clean_partner_sign_type(doc)", src, rel)


class GiaoDienVaKhaiBao(unittest.TestCase):
    def test_truong_va_trang(self):
        cr = json.loads(_read("approval_center/doctype/ec_contract_review_request/ec_contract_review_request.json"))
        f = next(x for x in cr["fields"] if x["fieldname"] == "partner_sign_type")
        self.assertEqual(f["fieldtype"], "Select")
        self.assertEqual([o for o in f["options"].split("\n") if o],
                         list(importlib.import_module(P + "domain.esign_flow").PARTNER_SIGN_TYPES))
        order = cr["field_order"]
        self.assertEqual(order.index("partner_sign_type"), order.index("partner_signer_identity") + 1)
        defn = _read("approval_center/features/contract_review/domain/definition.py")
        self.assertIn('"partner_sign_type")', defn)
        self.assertIn('"esign_partner_sign_types"', defn)
        html = _read("approval_center/features/contract_review/ui/main_section.html")
        self.assertIn('<select data-model="partner_sign_type">', html)
        self.assertIn("esign_partner_sign_types", html)
        self.assertIn('"Kiểu ký: "+signTypeLabel(biz.partner_sign_type)', html)
        self.assertNotIn("{{", html)

    def test_patch_resync_va_ban_ke(self):
        man = json.loads(_read("approval_center/patches/resync_manifest.json"))
        key = "approval_center/features/contract_review/ui/main_section.html"
        with open(os.path.join(APP, key), "rb") as fh:
            self.assertEqual(man[key]["sha256"], hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest())
        self.assertEqual(man[key]["last_resync_patch"], "p582_resync_hop_dong_kieu_ky_doi_tac")
        lines = [ln for ln in _read("patches.txt").splitlines() if ln.strip()]
        self.assertEqual(lines.count("ecentric_workspace.approval_center.patches.p582_resync_hop_dong_kieu_ky_doi_tac"), 1)
        html = _read(key)
        marks = re.search(r"_MARKS = \(([^)]*)\)", _read("approval_center/patches/p582_resync_hop_dong_kieu_ky_doi_tac.py"),
                          re.S).group(1)
        for m in re.findall(r'"([^"]+)"', marks):
            self.assertIn(m, html)


if __name__ == "__main__":
    unittest.main()
