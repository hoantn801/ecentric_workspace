# Copyright (c) 2026, eCentric and contributors
"""Chat Ky so 24/11/2026: cong ky CMC BAT BUOC CCCD / MST cua doi tac voi MOI hop dong co doi tac ky.
Truoc day external_handlers chi gui CCCD khi creator ca nhan ky chinh minh (trung email) -> creator cong
ty / nguoi ky khac email bi CMC tu choi.

  * partner_identity: o nhap tay > CCCD creator ca nhan ky chinh minh (trung email, hoac trung ten khi
    creator chua co email) > MST cong ty / ho kinh doanh (ho KD chua co MST -> CCCD chu ho);
    nguoi ky KHONG phai creator ca nhan -> bat nhap CCCD nguoi ky; hop dong khac -> bat nhap.
  * external_handlers LUON co `identity`, thieu thi nem loi ro rang.
  * esign_gate.before_submit bao thieu NGAY luc gui (chi khi phieu ky qua nen tang).
  * So CCCD / MST la PII: nguoi khong phai nguoi lap / SM / nguoi duoc tai ban du thay 3 ky tu cuoi.
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hop_dong_dinh_danh_doi_tac_24_11.py
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

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Throw, _fresh  # noqa: E402

APP = os.path.abspath(os.path.join(HERE, "..", ".."))
P = "ecentric_workspace.approval_center.features.contract_review.application."
KOL_TYPE = "KOL/KOC / Creator (EC)"
LABOR_TYPE = "Labor / Hợp đồng lao động (EC)"


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


def _doc(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type=KOL_TYPE, esign_flow="kol_wf09", creator="SUP-1",
            partner_signer_name="Nguyen Van A", partner_signer_email="a@gmail.com", requested_by="req@ec",
            owner="req@ec", partner_signer_identity=None)
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    return d


def _creator(**kw):
    row = dict({"ec_cr_type": "Cá nhân", "supplier_name": "Nguyễn Văn A", "ec_cr_email": "a@gmail.com",
                "ec_cr_cccd": "079 123 456 789", "ec_cr_cccd_issue_place": "Cục CS QLHC",
                "ec_cr_cccd_issue_date": "2021-05-03", "ec_cr_dob": "1999-12-31", "tax_id": None}, **kw)
    STATE["values"][("Supplier", "SUP-1")] = lambda field, as_dict: dict(row)
    return row


def _svc(user="req@ec"):
    svc, _v, _a, _f = _fresh(user)
    return svc


class DinhDanh(unittest.TestCase):
    def test_ca_nhan_ky_chinh_minh_gui_cccd_kem_noi_cap(self):
        svc = _svc()
        _creator()
        out, err = svc.partner_identity(_doc())
        self.assertIsNone(err)
        self.assertEqual(out, {"identity": "079123456789", "identity_place": "Cục CS QLHC",
                               "identity_date": "03/05/2021", "dob": "31/12/1999"})

    def test_creator_chua_co_email_trung_ten_van_la_chinh_creator(self):
        svc = _svc()
        _creator(ec_cr_email=None, supplier_name="Nguyen  van a")
        out, err = svc.partner_identity(_doc(partner_signer_email="khac@gmail.com"))
        self.assertIsNone(err)
        self.assertEqual(out["identity"], "079123456789")

    def test_nguoi_ky_khac_creator_phai_nhap_cccd_nguoi_ky(self):
        svc = _svc()
        _creator()
        out, err = svc.partner_identity(_doc(partner_signer_email="quanly@agency.vn", partner_signer_name="Tran B"))
        self.assertEqual(out, {})
        self.assertIn("không phải chính creator", err)
        out, err = svc.partner_identity(_doc(partner_signer_email="quanly@agency.vn",
                                             partner_signer_identity=" 001 099 000 111 "))
        self.assertEqual((out, err), ({"identity": "001099000111"}, None))   # khong kem noi cap cua creator

    def test_cong_ty_gui_mst_ke_ca_nguoi_ky_khac_email(self):
        svc = _svc()
        _creator(ec_cr_type="Công ty", tax_id="0312 345 678-001", ec_cr_cccd=None)
        out, err = svc.partner_identity(_doc(partner_signer_email="giamdoc@cty.vn"))
        self.assertEqual((out, err), ({"identity": "0312345678-001"}, None))
        _creator(ec_cr_type="Công ty", tax_id=None, ec_cr_cccd=None)
        out, err = svc.partner_identity(_doc())
        self.assertIn("chưa có MST", err)

    def test_ho_kinh_doanh_chua_co_mst_dung_cccd_chu_ho(self):
        svc = _svc()
        _creator(ec_cr_type="Hộ kinh doanh", tax_id=None)
        out, err = svc.partner_identity(_doc(partner_signer_email="x@y.vn"))
        self.assertEqual((out["identity"], err), ("079123456789", None))

    def test_ca_nhan_thieu_cccd(self):
        svc = _svc()
        _creator(ec_cr_cccd=None)
        self.assertIn("chưa có CCCD", svc.partner_identity(_doc())[1])

    def test_hop_dong_khac_kol_phai_nhap_tay(self):
        svc = _svc()
        d = _doc(contract_type=LABOR_TYPE, esign_flow="hd_lao_dong", creator=None)
        self.assertIn("CCCD / MST người ký phía đối tác", svc.partner_identity(d)[1])
        d["partner_signer_identity"] = "079123456789"
        self.assertEqual(svc.partner_identity(d), ({"identity": "079123456789"}, None))
        d["partner_signer_identity"] = "12-34"
        self.assertIn("không hợp lệ", svc.partner_identity(d)[1])

    def test_quy_trinh_khong_co_doi_tac_ky_thi_khong_kiem(self):
        svc = _svc()
        self.assertIsNone(svc.partner_identity_error(_doc(esign_flow="khong_ky_cong", creator=None,
                                                          contract_type=LABOR_TYPE)))
        _creator(ec_cr_cccd=None)
        self.assertTrue(svc.partner_identity_error(_doc()))


class GuiCong(unittest.TestCase):
    def test_external_handlers_luon_co_identity(self):
        _svc()
        hooks = importlib.import_module(P + "esign_hooks")
        _creator(ec_cr_type="Công ty", tax_id="0312345678")
        _doc(partner_signer_email="giamdoc@cty.vn", partner_signer_phone="0909")
        rows = hooks.external_handlers("CR-1")
        self.assertEqual(rows, [{"full_name": "Nguyen Van A", "email": "giamdoc@cty.vn", "phone": "0909",
                                 "identity": "0312345678"}])
        _creator(ec_cr_type="Công ty", tax_id=None, ec_cr_cccd=None)
        with self.assertRaises(Throw) as cm:
            hooks.external_handlers("CR-1")
        self.assertIn("MST", str(cm.exception))

    def test_gui_phieu_bao_thieu_ngay_khi_ky_qua_nen_tang(self):
        _svc()
        gate = importlib.import_module(P + "esign_gate")
        _creator(ec_cr_cccd=None)
        d = _doc(sign_pdf=None)
        gate.profile = lambda name: "HO-SO-KOL"
        gate.requester_signs = lambda name: False
        with self.assertRaises(Throw) as cm:
            gate.before_submit(d)
        self.assertIn("CCCD", str(cm.exception))                 # bao dinh danh TRUOC khi doi Ban PDF
        gate.profile = lambda name: None                          # khong ky so: khong chan
        self.assertFalse(gate.before_submit(d))


class CheSo(unittest.TestCase):
    def _redact(self, user, roles=()):
        _fresh(user)
        STATE["roles"][user] = list(roles)
        access = importlib.import_module(P + "kol_access")
        access.can_download_full = lambda b, u: False
        biz = {"contract_type": LABOR_TYPE, "requested_by": "req@ec", "owner": "req@ec",
               "partner_signer_identity": "079123456789"}
        access.redact_business(biz)
        return biz["partner_signer_identity"]

    def test_nguoi_khac_chi_thay_3_so_cuoi(self):
        self.assertEqual(self._redact("duyet@ec"), "•••789")
        self.assertEqual(self._redact("req@ec"), "079123456789")
        self.assertEqual(self._redact("admin@ec", ["System Manager"]), "079123456789")


class GiaoDienVaKhaiBao(unittest.TestCase):
    def test_truong_va_trang(self):
        cr = json.loads(_read("doctype/ec_contract_review_request/ec_contract_review_request.json"))
        f = next(x for x in cr["fields"] if x["fieldname"] == "partner_signer_identity")
        self.assertEqual(f["fieldtype"], "Data")
        self.assertIn("partner_signer_identity", cr["field_order"])
        self.assertIn('"partner_signer_identity"', _read("features/contract_review/domain/definition.py"))
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('data-model="partner_signer_identity"', html)
        self.assertNotIn("{{", html)
        svc_src = _read("features/contract_review/application/kol_service.py")
        self.assertIn('"partner_signer_identity")', svc_src.split("PARTNER_FIELDS =", 1)[1].split("\n", 1)[0])

    def test_patch_resync_va_ban_ke(self):
        man = json.loads(_read("patches/resync_manifest.json"))
        key = "approval_center/features/contract_review/ui/main_section.html"
        with open(os.path.join(APP, "features/contract_review/ui/main_section.html"), "rb") as fh:
            self.assertEqual(man[key]["sha256"], hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest())
        last = man[key]["last_resync_patch"]
        order = [ln.rsplit(".", 1)[-1] for ln in _read("../patches.txt").splitlines() if ln.strip()]
        self.assertIn(last, order)
        self.assertGreaterEqual(order.index(last), order.index("p545_resync_hop_dong_dinh_danh_doi_tac"))
        html = _read("features/contract_review/ui/main_section.html")
        marks = re.search(r"_MARKS = \(([^)]*)\)", _read("patches/p545_resync_hop_dong_dinh_danh_doi_tac.py")).group(1)
        for m in re.findall(r'"([^"]+)"', marks):
            self.assertIn(m, html)


if __name__ == "__main__":
    unittest.main()
