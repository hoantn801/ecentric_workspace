# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC - quy tac thuan (thue, so HD, han thanh toan, chu so, dien mau .docx).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_contract_kol_domain.py
"""
import datetime as dt
import io
import os
import sys
import unittest
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))

from ecentric_workspace.approval_center.features.contract_review.domain import (  # noqa: E402
    docx_fill, kol, vn_words)


def make_docx(body_xml, header_xml=None):
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
           'mc:Ignorable="w14"><w:body>%s</w:body></w:document>' % body_xml)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
        if header_xml:
            z.writestr("word/header1.xml", header_xml)
        z.writestr("word/media/logo.png", b"\x89PNG-binary")
    return buf.getvalue()


def doc_xml(data, part="word/document.xml"):
    return zipfile.ZipFile(io.BytesIO(data)).read(part).decode("utf-8")


class AmountTests(unittest.TestCase):
    def test_ca_nhan_thuc_nhan_quy_ve_gross(self):
        a = kol.compute_amounts("Cá nhân", kol.NET_AFTER_PIT, 9_000_000)
        self.assertEqual((a["gross"], a["pit"], a["payable"], a["contract_value"]),
                         (10_000_000, 1_000_000, 9_000_000, 10_000_000))

    def test_ca_nhan_gross(self):
        a = kol.compute_amounts("Cá nhân", kol.GROSS_BEFORE_PIT, 7_000_000)
        self.assertEqual((a["pit"], a["payable"]), (700_000, 6_300_000))

    def test_ca_nhan_thue_0_cho_khoan_nho(self):
        a = kol.compute_amounts("Cá nhân", kol.NET_AFTER_PIT, 1_500_000, pit_rate=0)
        self.assertEqual((a["gross"], a["pit"], a["payable"]), (1_500_000, 0, 1_500_000))

    def test_cong_ty_chua_vat(self):
        a = kol.compute_amounts("Công ty", kol.BEFORE_VAT, 15_000_000)
        self.assertEqual((a["vat"], a["payable"], a["contract_value"]),
                         (1_200_000, 16_200_000, 16_200_000))

    def test_cong_ty_da_vat_khop_so_sheet(self):
        # Sheet cu: 16.200.000 da VAT 8% -> truoc thue 15.000.000.
        a = kol.compute_amounts("Công ty", kol.WITH_VAT, 16_200_000)
        self.assertEqual((a["gross"], a["vat"]), (15_000_000, 1_200_000))

    def test_ho_kinh_doanh(self):
        a = kol.compute_amounts("Hộ kinh doanh", kol.HOUSEHOLD_TOTAL, 5_000_000)
        self.assertEqual((a["pit"], a["vat"], a["payable"]), (0, 0, 5_000_000))

    def test_kieu_nhap_khong_hop_loai_creator(self):
        with self.assertRaises(ValueError):
            kol.compute_amounts("Cá nhân", kol.BEFORE_VAT, 1_000_000)
        with self.assertRaises(ValueError):
            kol.compute_amounts("Công ty", kol.WITH_VAT, 0)

    def test_coc(self):
        self.assertEqual(kol.advance_amount(9_000_000, kol.PAY_ADVANCE, 30), 2_700_000)
        self.assertEqual(kol.advance_amount(9_000_000, kol.PAY_AFTER_ACCEPTANCE, 30), 0)
        with self.assertRaises(ValueError):
            kol.advance_amount(9_000_000, kol.PAY_ADVANCE, 100)


class DateAndNumberTests(unittest.TestCase):
    def test_han_thanh_toan_ngay_lich_doi_cuoi_tuan(self):
        # 03/11/2026 la thu Ba; +30 = 03/12 thu Nam.
        self.assertEqual(kol.due_date(dt.date(2026, 11, 3), 30), dt.date(2026, 12, 3))
        # 07/11/2026 (T7) + 30 = 07/12 la thu Hai -> giu nguyen.
        self.assertEqual(kol.due_date("2026-11-07", 30), dt.date(2026, 12, 7))
        # 05/11 + 30 = 05/12 la T7 -> 07/12 thu Hai.
        self.assertEqual(kol.due_date("2026-11-05", 30), dt.date(2026, 12, 7))
        self.assertIsNone(kol.due_date(None, 30))

    def test_so_hop_dong_dung_khuon_sheet_va_khong_trung(self):
        n = kol.contract_number("2026-03-15", "ntp", "fcv")
        self.assertEqual(n, "15032026/HDDV/ECENTRIC-NTP.FCV")
        self.assertEqual(kol.contract_number("2026-03-15", "NTP", "FCV", existing={n}), n + "-2")
        with self.assertRaises(ValueError):
            kol.contract_number("2026-03-15", "", "FCV")
        with self.assertRaises(ValueError):
            kol.contract_number("2026-03-15", "NTP", "")

    def test_chu_so(self):
        self.assertEqual(vn_words.amount_in_words(30_000_000), "Ba mươi triệu đồng chẵn")
        self.assertEqual(vn_words.amount_in_words(1_005_000_000),
                         "Một tỷ không trăm lẻ năm triệu đồng chẵn")
        self.assertEqual(vn_words.amount_in_words(21_000_005),
                         "Hai mươi mốt triệu không trăm lẻ năm đồng")
        self.assertEqual(vn_words.number_to_words(115), "một trăm mười lăm")

    def test_canh_bao_doanh_thu(self):
        self.assertEqual(kol.revenue_warning(10_000_000, 4_000_000, 6_000_000), "")
        self.assertIn("vượt", kol.revenue_warning(10_000_000, 4_000_000, 6_000_001))
        self.assertIn("chưa có doanh thu", kol.revenue_warning(0, 0, 1))

    def test_tran_chi(self):
        self.assertEqual(kol.acceptance_cap(False, 3e6, 5e6, 9e6), 0)
        self.assertEqual(kol.acceptance_cap(True, 3e6, 0, 9e6), 3e6)
        self.assertEqual(kol.acceptance_cap(True, 3e6, 9e6, 9e6), 9e6)


class DocxTests(unittest.TestCase):
    def test_placeholder_bi_xe_nhieu_run_van_dien_dung_va_giu_dinh_dang_run_khac(self):
        body = ('<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Bên B: </w:t></w:r>'
                '<w:r><w:t>{{ten_</w:t></w:r><w:r><w:t>creator}}</w:t></w:r>'
                '<w:r><w:t xml:space="preserve"> - CCCD {{cccd}}</w:t></w:r></w:p>')
        out, missing = docx_fill.fill_docx(make_docx(body), {"ten_creator": "Nguyễn A & B",
                                                             "cccd": "001"})
        xml = doc_xml(out)
        self.assertIn("<w:b/></w:rPr><w:t>Bên B: </w:t>", xml)
        self.assertIn("Nguyễn A &amp; B", xml)
        self.assertNotIn("{{", xml)
        self.assertIn("CCCD 001", xml)
        self.assertEqual(missing, [])
        self.assertIn('mc:Ignorable="w14"', xml)

    def test_bao_placeholder_khong_co_gia_tri(self):
        out, missing = docx_fill.fill_docx(make_docx('<w:p><w:r><w:t>{{la_gi}} {{cccd}}</w:t></w:r></w:p>'),
                                           {"cccd": "1"})
        self.assertEqual(missing, ["la_gi"])
        self.assertIn("{{la_gi}}", doc_xml(out))

    def test_header_cung_duoc_dien_va_tep_nhi_phan_giu_nguyen(self):
        head = ('<w:hdr xmlns:w="x"><w:p><w:r><w:t>Số {{so_hop_dong}}</w:t></w:r></w:p></w:hdr>')
        out, _ = docx_fill.fill_docx(make_docx("<w:p/>", head), {"so_hop_dong": "01/HDDV"})
        self.assertIn("Số 01/HDDV", doc_xml(out, "word/header1.xml"))
        self.assertEqual(zipfile.ZipFile(io.BytesIO(out)).read("word/media/logo.png"), b"\x89PNG-binary")

    def test_tim_placeholder_va_doc_van_ban(self):
        data = make_docx('<w:p><w:r><w:t>{{a</w:t></w:r><w:r><w:t>b}}</w:t></w:r></w:p>'
                         '<w:p><w:pPr/><w:r><w:t>Dòng 2</w:t></w:r></w:p>')
        self.assertEqual(docx_fill.find_placeholders(data), ["ab"])
        self.assertEqual(docx_fill.docx_text(data), "{{ab}}\nDòng 2")

    def test_reportlab(self):
        self.assertTrue(docx_fill.is_reportlab_pdf(b"%PDF-1.4 /Producer (ReportLab PDF Library)"))
        self.assertFalse(docx_fill.is_reportlab_pdf(b"%PDF-1.7 Microsoft Word"))

    def test_placeholder_mau_co_du_khoa_tren_trang_huong_dan(self):
        for key in ("so_hop_dong", "ten_creator", "cccd", "so_tien_bang_chu", "ngay_nghiem_thu"):
            self.assertIn(key, kol.PLACEHOLDER_HELP)

    def test_dien_mau_tu_phieu_that(self):
        doc = {"contract_no": "X", "payable_amount": 9_000_000, "contract_date": "2026-03-15",
               "pit_rate": 10, "vat_rate": 0}
        creator = {"supplier_name": "A", "ec_cr_cccd": "079", "ec_cr_dob": "1999-01-02"}
        v = kol.placeholders(doc, creator)
        self.assertEqual((v["ngay_ky"], v["ngay_sinh"], v["so_tien_thanh_toan"]),
                         ("15/03/2026", "02/01/1999", "9.000.000"))
        self.assertEqual(v["so_tien_bang_chu"], "Chín triệu đồng chẵn")


if __name__ == "__main__":
    unittest.main()
