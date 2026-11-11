# Copyright (c) 2026, eCentric and contributors
"""Khoa cac loi QC vong 2 (12/11/2026, agent Opus) cua dot "dung lai 18 mau tool cu".

  * Ngay khong ghi nam: lay lan gan nhat voi moc (ngay ghi du nam trong o, khong co thi ngay tao
    phieu), go khong theo thu tu van dung; khoang ngay "05-06/12" bi bao; nam / khoang cach vo ly bi bao.
  * Cong ty co coc: VAT nam o phan con lai, cac BBNT cong lai khop hoa don.
  * Ma doi tac co dau cach van dung; ten kieu cu {{x}} / ten cu snake_case doc duoc.
  * Doan chi con dau cau / ngat dong sau khi bo placeholder rong thi xoa; con chu khac thi GIU.
  * Patch p365 chi sua phieu nhap, khong nem loi.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_contract_kol_qc2_12_11.py
"""
import datetime as dt
import importlib
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))
sys.path.insert(0, _HERE)

from test_contract_kol_domain import doc_xml, make_docx  # noqa: E402

from ecentric_workspace.approval_center.features.contract_review.domain import (  # noqa: E402
    docx_fill, kol_texts as T, kol_values as V)

L, G = "&lt;&lt;", "&gt;&gt;"
D = dt.date


def p(*runs):
    return "<w:p>" + "".join(runs) + "</w:p>"


def r(text):
    return '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % text


class ServiceDates(unittest.TestCase):
    def parse(self, text, today=D(2026, 11, 12)):
        return T.parse_service_dates(text, today)

    def test_khong_nam_lay_lan_gan_nhat_voi_ngay_tao(self):
        self.assertEqual(self.parse("05/01"), [D(2027, 1, 5)])                    # thang 11 go "05/01" = sang nam
        self.assertEqual(self.parse("05/11"), [D(2026, 11, 5)])                   # lui vai ngay: van nam nay
        self.assertEqual(self.parse("28/12, 05/01", D(2026, 12, 20)), [D(2026, 12, 28), D(2027, 1, 5)])

    def test_go_khong_theo_thu_tu_van_dung(self):
        self.assertEqual(self.parse("05/01, 28/12", D(2026, 12, 20)), [D(2026, 12, 28), D(2027, 1, 5)])

    def test_ngay_co_nam_lam_moc_cho_ngay_khong_nam(self):
        self.assertEqual(self.parse("28/12/2026, 03/01"), [D(2026, 12, 28), D(2027, 1, 3)])
        self.assertEqual(self.parse("03/01, 28/12/2026"), [D(2026, 12, 28), D(2027, 1, 3)])

    def test_khoang_ngay_bi_bao_ro_cach_viet(self):
        for text in ("05-06/12", "05 - 10/12/2026"):
            with self.assertRaises(ValueError) as cm:
                self.parse(text)
            self.assertIn("khoảng ngày", str(cm.exception))
        self.assertEqual(self.parse("2026-12-05"), [D(2026, 12, 5)])               # ISO khong phai khoang

    def test_nam_vo_ly_va_cach_qua_xa_bi_bao(self):
        with self.assertRaises(ValueError):
            self.parse("05/12/2030")
        with self.assertRaises(ValueError):
            self.parse("05/12/2024")
        with self.assertRaises(ValueError):
            self.parse("05/01/2027, 28/12/2027")

    def test_moi_ngay_mot_dong_dan_tu_sheets(self):
        self.assertEqual(self.parse("05/12\n06/12\r\n12/12"), [D(2026, 12, 5), D(2026, 12, 6), D(2026, 12, 12)])
        # O nhap mot dong bien xuong dong thanh dau cach
        self.assertEqual(self.parse("05/12 06/12"), [D(2026, 12, 5), D(2026, 12, 6)])

    def test_ngay_khong_ton_tai(self):
        with self.assertRaises(ValueError):
            self.parse("31/02/2027")


class CompanyDepositRounds(unittest.TestCase):
    # Truoc VAT 10tr, VAT 8% -> 10.8tr; coc 40% tren truoc VAT = 4tr (khong VAT).
    DOC = {"payable_amount": 10_800_000, "gross_amount": 10_000_000, "advance_amount": 4_000_000}

    def test_mot_dot_phan_con_lai_mang_toan_bo_vat(self):
        m = V.round_money("Công ty", 6_800_000, None, 8, self.DOC)
        self.assertEqual((m["pre_vat"], m["vat"], m["total"]), (6_000_000, 800_000, 6_800_000))

    def test_hai_dot_cong_lai_khop_hoa_don(self):
        a = V.round_money("Công ty", 3_400_000, None, 8, self.DOC)
        b = V.round_money("Công ty", 3_400_000, None, 8, self.DOC)
        self.assertEqual(a["pre_vat"] + b["pre_vat"] + 4_000_000, 10_000_000)
        self.assertEqual(a["vat"] + b["vat"], 800_000)


class NoDatesStillDescribed(unittest.TestCase):
    """QC3: khong doc duoc ngay (affiliate / phieu cu chu tu do) van phai co mo ta cong viec + thanh toan."""

    def values(self, **kw):
        doc = dict({"creator_type": "Cá nhân", "service_type": "Hoa hồng affiliate", "brand": "FCV",
                    "payable_amount": 9_000_000, "gross_amount": 10_000_000}, **kw)
        return V.contract_values(doc, {"supplier_name": "A"}, "FCV", D(2026, 11, 12), [])

    def test_bbnt_va_hop_dong_khong_trong_mo_ta(self):
        v = self.values()
        for k in ("BBNT_WORK_DESCRIPTION_SHORT", "BBNT_PAYMENT_DESCRIPTION", "OBJECT_PARAGRAPH",
                  "WORK_CONTENT_PARAGRAPH"):
            self.assertTrue(v[k].strip(), k)

    def test_dong_ngay_lay_nguyen_van_chu(self):
        v = self.values(service_type="Livestream", air_dates="cuối tháng 12")
        self.assertIn("cuối tháng 12", v["DETAIL_PARAGRAPH"])
        self.assertNotIn(": .", v["DETAIL_PARAGRAPH"])

    def test_affiliate_khong_doi_ngay_bbnt_tren_hop_dong(self):
        v = self.values()
        self.assertEqual(V.empty_required(v, ["BBNT_DAY", "SERVICE_START_SLASH"], "Cá nhân", "Hoa hồng affiliate"), [])
        self.assertEqual(V.empty_required(v, ["BBNT_DAY"], "Cá nhân", "Livestream"), ["BBNT_DAY"])


class PartyCodeAndLabels(unittest.TestCase):
    def test_ma_tay_co_dau_cach(self):
        self.assertEqual(T.party_code("Cá nhân", "Nguyễn Thị Phương", " n tp "), "NTP")
        self.assertEqual(T.party_code("Công ty", "Công ty TNHH ABC Media", "a m"), "AM")

    def test_nhan_ten_cu(self):
        self.assertEqual(V.missing_labels(["cccd"]), ["CCCD"])
        self.assertTrue(V.missing_is_creator(["cccd"]))
        self.assertIn("báo Kế toán", V.missing_labels(["{{ngay_sinh}}"])[0])
        self.assertIn("lỗi định dạng", V.missing_labels(["CONTRACT_NO (không điền được)"])[0])


class DropRule(unittest.TestCase):
    DROP = V.CONDITIONAL_LINES

    def test_doan_chi_con_ngat_dong_va_dau_cau_bi_xoa(self):
        body = p(r("- " + L + "ADVANCE_VIDEO_DATE_LINE" + G), "<w:r><w:br/></w:r>", r(";")) + p(r("Sau"))
        out, missing = docx_fill.fill_docx(make_docx(body), {"ADVANCE_VIDEO_DATE_LINE": ""}, self.DROP)
        x = doc_xml(out)
        self.assertNotIn("<w:br/>", x)
        self.assertIn("Sau", x)
        self.assertEqual(missing, [])

    def test_doan_con_chu_khac_thi_giu(self):
        body = p(r("Ghi chú cọc: " + L + "ADVANCE_VIDEO_DATE_LINE" + G))
        out, _m = docx_fill.fill_docx(make_docx(body), {"ADVANCE_VIDEO_DATE_LINE": ""}, self.DROP)
        self.assertIn("Ghi chú cọc:", doc_xml(out))

    def test_placeholder_khong_tuy_chon_khong_bi_xoa_doan(self):
        body = p(r("Số: " + L + "CONTRACT_NO" + G))
        out, _m = docx_fill.fill_docx(make_docx(body), {"CONTRACT_NO": "X1"}, self.DROP)
        self.assertIn("Số: X1", doc_xml(out))


class PatchP365(unittest.TestCase):
    def setUp(self):
        self.calls = []
        fk = types.ModuleType("frappe")
        fk.db = types.SimpleNamespace(
            exists=lambda *a, **k: True,
            set_value=lambda dt_, name, upd, update_modified=True: self.calls.append((name, upd, update_modified)))
        row = lambda **k: types.SimpleNamespace(**k)  # noqa: E731
        self.rows = [
            row(name="A", creation="2026-11-11 22:00:00", contract_date="2026-11-11", creator_type="Cá nhân",
                payment_term_days=30),
            row(name="B", creation="2026-11-11 22:00:00", contract_date="2026-12-04", creator_type="Công ty",
                payment_term_days=30),
            row(name="C", creation="2026-11-11 22:00:00", contract_date=None, creator_type="Cá nhân",
                payment_term_days=45),
            row(name="D", creation="2026-11-11 22:00:00", contract_date=None, creator_type="Công ty",
                platform="Shopee", payment_term_days=30)]
        for x in self.rows:
            x.platform = getattr(x, "platform", "TikTok")
        self.comments = []
        fk.get_doc = lambda d: types.SimpleNamespace(insert=lambda **k: self.comments.append(d["reference_name"]))
        self.filters = []
        fk.get_all = lambda dt_, filters=None, **kw: (self.filters.append(filters), self.rows)[1]
        fk.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
        fk.log_error = lambda *a, **k: self.fail("p365 khong duoc loi: %s" % (a,))
        fk.get_traceback = lambda: ""
        self._saved = sys.modules.get("frappe")
        sys.modules["frappe"] = fk
        sys.modules.pop("ecentric_workspace.approval_center.patches.p365_chuan_hoa_nhap_kol_11_11", None)
        self.mod = importlib.import_module("ecentric_workspace.approval_center.patches.p365_chuan_hoa_nhap_kol_11_11")

    def tearDown(self):
        if self._saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = self._saved
        sys.modules.pop("ecentric_workspace.approval_center.patches.p365_chuan_hoa_nhap_kol_11_11", None)

    def test_chi_sua_dung_hai_gia_tri_cua_phieu_nhap(self):
        self.mod.execute()
        self.assertEqual(self.filters[0]["approval_request"], ["is", "not set"])
        self.assertEqual(self.calls, [("A", {"contract_date": None, "payment_term_days": 35}, False),
                                      ("D", {"payment_term_days": 15}, False)])
        self.assertEqual(self.comments, ["A", "D"])           # vet tren tung phieu bi sua


if __name__ == "__main__":
    unittest.main()
