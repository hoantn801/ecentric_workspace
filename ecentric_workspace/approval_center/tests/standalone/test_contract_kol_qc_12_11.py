# Copyright (c) 2026, eCentric and contributors
"""Khoa cac loi QC vong 1 (12/11/2026, 3 agent Opus) cua dot "dung lai 18 mau tool cu" - tang domain.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_contract_kol_qc_12_11.py
"""
import datetime as dt
import io
import os
import sys
import unittest
import xml.dom.minidom
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))
sys.path.insert(0, _HERE)

from test_contract_kol_domain import doc_xml, make_docx  # noqa: E402

from ecentric_workspace.approval_center.features.contract_review.domain import (  # noqa: E402
    docx_fill, kol, kol_texts as T, kol_values as V, vn_words)

L, G = "&lt;&lt;", "&gt;&gt;"


def p(text):
    return '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % text


def valid(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    for name in z.namelist():
        if name.endswith(".xml") and name.startswith("word/"):
            xml.dom.minidom.parseString(z.read(name))


class DocxRobust(unittest.TestCase):
    DROP = V.CONDITIONAL_LINES

    def test_doan_rong_tu_dong_khong_keo_xoa_ca_o_bang(self):
        # Word/Google hay ghi doan rong tu dong <w:p .../>: regex cu khop tu day toi </w:p> cua o sau,
        # xoa dong tuy chon la xoa luon ranh gioi o / hang.
        body = ('<w:tbl><w:tr><w:tc><w:p w:rsidR="00AB12CD"/></w:tc><w:tc>' + p("A") + '</w:tc></w:tr>'
                '<w:tr><w:tc>' + p(L + "ADVANCE_VIDEO_DATE_LINE" + G) + '</w:tc><w:tc>' + p("B") + '</w:tc></w:tr></w:tbl>')
        out, missing = docx_fill.fill_docx(make_docx(body), {"ADVANCE_VIDEO_DATE_LINE": ""}, self.DROP)
        x = doc_xml(out)
        valid(out)
        self.assertEqual(x.count("<w:tc>"), 4)
        self.assertEqual(x.count("<w:tr>"), 2)
        self.assertNotIn("ADVANCE_VIDEO_DATE_LINE", x)
        self.assertEqual(missing, [])

    def test_o_bang_chi_con_bookmark_van_co_doan(self):
        body = ('<w:tbl><w:tr><w:tc><w:tcPr/>' + p(L + "ADVANCE_LIVE_DATE_LINE" + G)
                + '<w:bookmarkEnd w:id="0"/></w:tc></w:tr></w:tbl>')
        out, _m = docx_fill.fill_docx(make_docx(body), {"ADVANCE_LIVE_DATE_LINE": ""}, self.DROP)
        x = doc_xml(out)
        self.assertIn("<w:p/></w:tc>", x)
        valid(out)

    def test_doan_co_ngat_section_hoac_khung_khong_bi_xoa(self):
        body = ('<w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:t>' + L + "ADVANCE_AFFILIATE_CLAUSE" + G + '</w:t></w:r></w:p>')
        out, _m = docx_fill.fill_docx(make_docx(body), {"ADVANCE_AFFILIATE_CLAUSE": ""}, self.DROP)
        x = doc_xml(out)
        self.assertIn("<w:sectPr/>", x)
        self.assertNotIn("ADVANCE_AFFILIATE_CLAUSE", x)

    def test_ky_tu_dieu_khien_khong_lam_hong_xml(self):
        out, _m = docx_fill.fill_docx(make_docx(p(L + "DURATION_DISPLAY" + G)), {"DURATION_DISPLAY": "60\x0bphút\x01"})
        valid(out)
        self.assertIn("60phút", doc_xml(out))

    def test_mau_con_ten_kieu_cu_bi_bao(self):
        data = make_docx(p("Bên B: {{ten_creator}}") + p(L + "CONTRACT_NO" + G))
        out, missing = docx_fill.fill_docx(data, {"CONTRACT_NO": "X"})
        self.assertIn("{{ten_creator}}", missing)
        self.assertIn("{{ten_creator}}", docx_fill.find_placeholders(data))
        self.assertIn("báo Kế toán", V.missing_labels(["{{ten_creator}}"])[0])


class MoneyAndWords(unittest.TestCase):
    def test_lam_tron_nua_len_nhu_tool_cu(self):
        self.assertEqual(T.money(2_500_000.5), "2,500,001")      # format() cua Python ra ...000 (lam tron chan)
        self.assertEqual(T.money(1_000_000), "1,000,000")
        self.assertEqual(vn_words.amount_in_words(2.5), "Ba đồng")


class PaymentDaysAndAdvance(unittest.TestCase):
    def test_15_ngay_chi_cho_cong_ty_shopee(self):
        self.assertEqual(kol.default_payment_days("Công ty", "Shopee"), 15)
        self.assertEqual(kol.default_payment_days("Cá nhân", "Shopee"), 35)
        self.assertEqual(kol.default_payment_days("Hộ kinh doanh", "TikTok"), 30)

    def test_payment_days_hddv_bbnt_ngoai_shopee_lay_so_ngay_cong_ty(self):
        base = {"service_type": "Livestream", "platform": "TikTok", "contract_no": "X"}
        person = V.contract_values(dict(base, creator_type="Cá nhân"), {}, "", None, [dt.date(2026, 12, 5)], payment_days=35)
        self.assertEqual((person["PAYMENT_DAYS_PERSONAL"], person["PAYMENT_DAYS_HDDV"], person["PAYMENT_DAYS_BBNT"]),
                         ("35", "30", "30"))
        comp = V.contract_values(dict(base, creator_type="Công ty"), {}, "", None, [dt.date(2026, 12, 5)], payment_days=45)
        self.assertEqual((comp["PAYMENT_DAYS_HDDV"], comp["PAYMENT_DAYS_BBNT"]), ("45", "45"))
        shopee = V.contract_values(dict(base, creator_type="Công ty", platform="Shopee"), {}, "", None,
                                   [dt.date(2026, 12, 5)], payment_days=15)
        self.assertEqual((shopee["PAYMENT_DAYS_HDDV"], shopee["PAYMENT_DAYS_BBNT"]), ("30", "15"))

    def test_mau_co_coc_cho_phieu_khong_coc_bi_bao_thieu(self):
        vals = V.contract_values({"creator_type": "Cá nhân", "contract_no": "X"}, {}, "", None, [dt.date(2026, 12, 5)])
        miss = V.empty_required(vals, ["ADVANCE_AMOUNT_NUM", "BALANCE_AMOUNT_NUM"], "Cá nhân")
        self.assertEqual(sorted(miss), ["ADVANCE_AMOUNT_NUM", "BALANCE_AMOUNT_NUM"])


class AcceptanceRounds(unittest.TestCase):
    DOC = {"creator_type": "Cá nhân", "pit_rate": 10, "gross_amount": 10_000_000, "pit_amount": 1_000_000,
           "payable_amount": 9_000_000, "contract_no": "X", "service_type": "Livestream"}

    def _contract(self, doc):
        return V.contract_values(doc, {}, "", None, [dt.date(2026, 12, 5)])

    def test_dot_le_tinh_lai_so_tien_theo_dot(self):
        doc = dict(self.DOC, acceptances=[{}, {}])
        v = V.acceptance_values(self._contract(doc), {"idx": 2, "amount": 3_000_000}, doc)
        self.assertEqual((v["NET_AMOUNT_NUM"], v["GROSS_AMOUNT_NUM"]), ("3,000,000", "3,333,333"))
        self.assertEqual(V.printed_amount(doc, 3_000_000), 3_000_000)

    def test_mot_dot_phu_ca_hop_dong_giu_so_hop_dong(self):
        doc = dict(self.DOC, acceptances=[{}])
        v = V.acceptance_values(self._contract(doc), {"idx": 1, "amount": 9_000_000}, doc)
        self.assertEqual((v["NET_AMOUNT_NUM"], v["GROSS_AMOUNT_NUM"]), ("9,000,000", "10,000,000"))

    def test_hop_dong_coc_mot_dot_phan_con_lai_van_la_100_phan_tram(self):
        doc = dict(self.DOC, advance_amount=3_600_000, acceptances=[{}])
        v = V.acceptance_values(self._contract(doc), {"idx": 1, "amount": 5_400_000}, doc)
        self.assertEqual(v["NET_AMOUNT_NUM"], "9,000,000")
        self.assertEqual(V.printed_amount(doc, 5_400_000), 9_000_000)

    def test_cong_ty_dot_le_quy_ve_truoc_vat(self):
        doc = {"creator_type": "Công ty", "vat_rate": 8, "gross_amount": 10_000_000, "vat_amount": 800_000,
               "payable_amount": 10_800_000, "acceptances": [{}, {}]}
        v = V.acceptance_values(self._contract(doc), {"idx": 1, "amount": 5_400_000}, doc)
        self.assertEqual((v["TOTAL_AMOUNT_NUM"], v["PRE_VAT_AMOUNT_NUM"], v["VAT_AMOUNT_NUM"]),
                         ("5,400,000", "5,000,000", "400,000"))


if __name__ == "__main__":
    unittest.main()
