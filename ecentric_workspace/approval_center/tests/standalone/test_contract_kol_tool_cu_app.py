# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL theo tool cu - tang application chay voi frappe gia (khong can bench).

  * Ngay ky lui ve 1 ngay lam viec truoc buoi dau (bo T7/CN/ngay nghi), chon sau buoi dau thi lui.
  * So ngay thanh toan mac dinh 35/30/30/Shopee 15; doi loai creator thi doi theo neu dang la mac dinh.
  * So hop dong lay buoi dau + ma doi tac suy tu ten.
  * Chon mau: Shopee rieng, coc phai dung mau coc, Livestream + Video dung mau Livestream.
  * Dien mau that (BBNT ca nhan cua Ke toan): khong sot <<...>>, dong tuy chon rong bi xoa.
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

PKG = "ecentric_workspace.approval_center.features.contract_review.application"


class _Throw(Exception):
    pass


class FakeDoc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def as_dict(self):
        return dict(self)


def _fake_frappe(state):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})

    def throw(msg, exc=None):
        raise _Throw(msg)
    fk.throw = throw
    fk.session = types.SimpleNamespace(user="a@ecentric.vn")
    fk.db = types.SimpleNamespace(
        get_value=lambda dt_, name, field=None, as_dict=False: state["stored"].get(name) if as_dict else None,
        exists=lambda *a, **k: False)
    def get_all(doctype, filters=None, **kw):
        rows = state["get_all"].get(doctype, [])
        eq = {k: v for k, v in (filters or {}).items() if not isinstance(v, (list, tuple)) and k != "is_active"}
        return [r for r in rows if not isinstance(r, dict) or all(r.get(k) == v for k, v in eq.items())]
    fk.get_all = get_all
    fk.get_cached_value = lambda *a, **k: "HL"
    fk.defaults = types.SimpleNamespace(get_global_default=lambda k: "eCentric")
    fk.get_roles = lambda u=None: []
    utils = types.ModuleType("frappe.utils")
    utils.today = lambda: "2026-11-12"
    utils.now_datetime = lambda: dt.datetime(2026, 11, 12, 9)
    utils.nowdate = utils.today
    utils.flt = lambda v: float(v or 0)
    fk.utils = utils
    return fk


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = {"stored": {}, "get_all": {}}
        fk = _fake_frappe(cls.state)
        cls._saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
        sys.modules["frappe"], sys.modules["frappe.utils"] = fk, fk.utils
        for m in ("kol_lookup", "kol_service", "kol_files"):
            sys.modules.pop(PKG + "." + m, None)
        cls.lookup = importlib.import_module(PKG + ".kol_lookup")
        cls.svc = importlib.import_module(PKG + ".kol_service")
        cls.files = importlib.import_module(PKG + ".kol_files")
        cls.lookup.brand_code = lambda brand: "FCV" if brand else ""

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for m in ("kol_lookup", "kol_service", "kol_files"):
            sys.modules.pop(PKG + "." + m, None)

    def setUp(self):
        self.state["stored"].clear()
        self.state["get_all"].clear()
        self.state["get_all"]["Holiday"] = []

    # ---------------------------------------------------------- ngay ky
    def test_ngay_ky_lui_ve_ngay_lam_viec_truoc_buoi_dau(self):
        doc = FakeDoc(air_dates="05,06/12/2026")          # 05/12/2026 la thu Bay
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-04")
        doc = FakeDoc(air_dates="07/12/2026", contract_date="2026-12-10")   # chon SAU buoi dau
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-04")                  # T2 07/12 -> T6 04/12
        self.state["get_all"]["Holiday"] = [dt.date(2026, 12, 4)]
        doc = FakeDoc(air_dates="07/12/2026")
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-03")
        doc = FakeDoc(air_dates="", contract_date=None)
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-11-12")                  # chua co ngay: hom nay

    def test_ngay_bbnt_du_kien_sau_buoi_cuoi(self):
        self.assertEqual(self.svc.expected_bbnt_date(FakeDoc(air_dates="04,11/12/2026")), dt.date(2026, 12, 14))

    # ---------------------------------------------------------- so ngay thanh toan
    def test_so_ngay_thanh_toan_mac_dinh_theo_tool_cu(self):
        doc = FakeDoc(creator_type="Cá nhân", platform="TikTok")
        self.svc._default_payment_days(doc)
        self.assertEqual(doc.payment_term_days, 35)
        doc = FakeDoc(creator_type="Công ty", platform="Shopee")
        self.svc._default_payment_days(doc)
        self.assertEqual(doc.payment_term_days, 15)
        # Doi Ca nhan -> Cong ty khi o van la mac dinh cu (35): doi sang 30.
        self.state["stored"]["CR-1"] = {"creator_type": "Cá nhân", "platform": "TikTok"}
        doc = FakeDoc(name="CR-1", creator_type="Công ty", platform="TikTok", payment_term_days=35)
        self.svc._default_payment_days(doc)
        self.assertEqual(doc.payment_term_days, 30)
        # Nguoi dung da go so rieng: giu.
        doc = FakeDoc(name="CR-1", creator_type="Công ty", platform="TikTok", payment_term_days=45)
        self.svc._default_payment_days(doc)
        self.assertEqual(doc.payment_term_days, 45)

    # ---------------------------------------------------------- so hop dong
    def test_so_hop_dong_lay_buoi_dau_va_ma_suy_tu_ten(self):
        doc = FakeDoc(name="CR-2", air_dates="21,22/07/2026", contract_date="2026-07-20", brand="FCV")
        self.svc.assign_number(doc, {"ec_cr_type": "Cá nhân", "supplier_name": "Nguyễn Thị Phương"})
        self.assertEqual(doc.contract_no, "21072026/HDDV/ECENTRIC-NTP.FCV")
        doc = FakeDoc(name="CR-3", air_dates="21/07/2026", brand="FCV")
        self.svc.assign_number(doc, {"ec_cr_type": "Công ty", "supplier_name": "Công ty TNHH ABC Media",
                                     "ec_cr_party_code": "CONGTY"})
        self.assertEqual(doc.contract_no, "21072026/HDDV/ECENTRIC-AM.FCV")

    # ---------------------------------------------------------- chon mau
    def _tpl(self, name, kind, ctype, service="Tất cả", platform="Tất cả", adv=0):
        return FakeDoc(name=name, kind=kind, creator_type=ctype, service_type=service, platform=platform,
                       has_advance=adv)

    def test_chon_mau_giong_tool_cu(self):
        H, B = "Hợp đồng", "BBNT"
        self.state["get_all"]["EC Contract Template"] = [
            self._tpl("HD-CN", H, "Cá nhân"), self._tpl("HD-CN-LIVE", H, "Cá nhân", "Livestream"),
            self._tpl("HD-CN-VIDEO", H, "Cá nhân", "Video"), self._tpl("HD-CN-COC", H, "Cá nhân", adv=1),
            self._tpl("HD-CT", H, "Công ty"), self._tpl("HD-CT-SHOPEE", H, "Công ty", "Livestream", "Shopee"),
            self._tpl("BB-CN-LIVE", B, "Cá nhân", "Livestream")]
        pick = self.lookup.pick_template
        self.assertEqual(pick(H, "Cá nhân", "Livestream + Video", False, "TikTok"), "HD-CN-LIVE")
        self.assertEqual(pick(H, "Cá nhân", "Video", False, "TikTok"), "HD-CN-VIDEO")
        self.assertEqual(pick(H, "Cá nhân", "Video", True, "TikTok"), "HD-CN-COC")      # coc: chi mau coc
        self.assertIsNone(pick(H, "Công ty", "Livestream", True, "TikTok"))              # khong lay mau thuong
        self.assertEqual(pick(H, "Công ty", "Livestream", False, "TikTok"), "HD-CT")      # khong lay mau Shopee
        self.assertEqual(pick(H, "Công ty", "Livestream", False, "Shopee"), "HD-CT-SHOPEE")
        self.assertEqual(pick(B, "Cá nhân", "Video", True, "TikTok"), None)               # BBNT video chua co
        self.assertEqual(pick(B, "Cá nhân", "Livestream", True, "TikTok"), "BB-CN-LIVE")  # BBNT khong xet coc


class FillRealTemplate(unittest.TestCase):
    """Dien mau BBNT ca nhan that cua Ke toan (van ban lay tu Google Docs 12/11, giu nguyen ten <<...>>)."""
    BBNT_PERSON = [
        "Hôm nay, ngày <<BBNT_DAY>> tháng <<BBNT_MONTH>> năm <<BBNT_YEAR>> tại TP.HCM, giữa hai Bên:",
        "<<PERSON_FULL_NAME>>", "<<PERSON_ID_NO>>", "<<PERSON_DOB>>", "<<PARTY_ADDRESS>>", "<<PARTY_TAX_ID>>",
        "<<PERSON_PHONE>>", "<<BANK_ACCOUNT_NO>>", "<<BANK_NAME_SHORT>>",
        "Căn cứ vào Hợp đồng hợp tác số <<CONTRACT_NO>> ký ngày <<SIGN_DATE_DOT>>",
        "* Thỏa thuận công việc được thực hiện thành công trên kênh TikTok <<CHANNEL_URL>>",
        "<<BBNT_WORK_DESCRIPTION_SHORT>>", "<<SERVICE_DATES_DISPLAY>>", "<<QUANTITY_DISPLAY>>",
        "<<BBNT_PAYMENT_DESCRIPTION>>", "<<GROSS_AMOUNT_NUM>> VNĐ", "(Bằng chữ:) <<GROSS_AMOUNT_WORDS>>",
        "*Chưa khấu trừ thuế TNCN <<TNCN_RATE_PCT>>%",
        "- Bên A sẽ khấu trừ <<TNCN_RATE_PCT>>% thuế TNCN và thanh toán số tiền thực nhận tương đương "
        "<<NET_AMOUNT_NUM>> VNĐ (Bằng chữ: <<NET_AMOUNT_WORDS>>) trong vòng <<PAYMENT_DAYS_PERSONAL>> ngày",
        "NGUYỄN VĂN LÃM", "<<SIGNATORY_B_UPPER>>",
        "Đính kèm Biên bản nghiệm thu hợp đồng Số <<CONTRACT_NO>> ký ngày <<SIGN_DATE_SLASH>>",
    ]

    @staticmethod
    def _docx(lines, cell_lines=()):
        esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
        body = "".join("<w:p><w:r><w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>" % esc(t) for t in lines)
        if cell_lines:
            body += "<w:tbl><w:tr><w:tc><w:tcPr/>%s</w:tc></w:tr></w:tbl>" % "".join(
                "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % esc(t) for t in cell_lines)
        return make_docx(body)

    def test_bbnt_ca_nhan_khong_sot_va_dung_so(self):
        from ecentric_workspace.approval_center.features.contract_review.domain import (
            docx_fill, kol, kol_values)
        amounts = kol.compute_amounts("Cá nhân", kol.NET_AFTER_PIT, 9_000_000, 10)
        doc = {"contract_no": "05122026/HDDV/ECENTRIC-NTP.FCV", "creator_type": "Cá nhân", "brand": "Vinasoy",
               "service_type": "Livestream", "platform": "TikTok", "quantity": 2, "pit_rate": 10,
               "gross_amount": amounts["gross"], "pit_amount": amounts["pit"], "payable_amount": amounts["payable"]}
        creator = {"supplier_name": "Nguyễn Thị Phương", "ec_cr_type": "Cá nhân", "ec_cr_cccd": "079",
                   "ec_cr_dob": "1999-01-02", "ec_cr_address": "12 Lê Lợi, Q1", "ec_phone": "09",
                   "ec_bank_account_no": "123", "ec_bank_name": "ACB", "ec_cr_tiktok_id": "phuong"}
        base = kol_values.contract_values(doc, creator, "FCV", "2026-12-04",
                                          [dt.date(2026, 12, 5), dt.date(2026, 12, 6)], payment_days=35)
        values = kol_values.acceptance_values(dict(base, BBNT_DAY="08", BBNT_MONTH="12", BBNT_YEAR="2026"),
                                              {"idx": 1, "amount": 9_000_000})
        out, missing = docx_fill.fill_docx(self._docx(self.BBNT_PERSON), values, kol_values.CONDITIONAL_LINES)
        xml = doc_xml(out)
        self.assertEqual(missing, [])
        self.assertNotIn("&lt;&lt;", xml)
        for want in ("10,000,000 VNĐ", "Mười triệu đồng", "9,000,000 VNĐ", "Chín triệu đồng",
                     "trong vòng 35 ngày", "NGUYỄN THỊ PHƯƠNG", "ký ngày 04.12.2026", "ký ngày 04/12/2026",
                     "12 Lê Lợi, Q1, Việt Nam", "https://www.tiktok.com/@phuong", "02 buổi",
                     "05.12.2026</w:t><w:br/><w:t xml:space=\"preserve\">06.12.2026",
                     "thông qua phát trực tiếp trên nền tảng Tik Tok."):
            self.assertIn(want, xml)

    def test_dong_tuy_chon_rong_bi_xoa_ca_doan_va_o_bang_con_doan_trong(self):
        from ecentric_workspace.approval_center.features.contract_review.domain import docx_fill, kol_values
        values = {"ADVANCE_LIVE_DATE_LINE": "Ngày thực hiện: 05/12/2026", "ADVANCE_VIDEO_DATE_LINE": "",
                  "PERSON_ID_FRONT_IMAGE": "", "PERSON_ID_BACK_IMAGE": ""}
        data = self._docx(["Trước", "<<ADVANCE_VIDEO_DATE_LINE>>", "<<ADVANCE_LIVE_DATE_LINE>>",
                           "<<PERSON_ID_FRONT_IMAGE>><<PERSON_ID_BACK_IMAGE>>", "Sau"],
                          cell_lines=["<<ADVANCE_VIDEO_DATE_LINE>>"])
        out, missing = docx_fill.fill_docx(data, values, kol_values.CONDITIONAL_LINES)
        xml = doc_xml(out)
        self.assertEqual(missing, [])
        self.assertNotIn("ADVANCE_VIDEO_DATE_LINE", xml)
        self.assertNotIn("PERSON_ID", xml)
        self.assertIn("Ngày thực hiện: 05/12/2026", xml)
        self.assertIn("<w:tcPr/><w:p/></w:tc>", xml)          # o bang van con mot doan van
        self.assertIn(">Trước<", xml)
        self.assertIn(">Sau<", xml)

    def test_nhan_thieu_tieng_viet(self):
        from ecentric_workspace.approval_center.features.contract_review.domain import kol_values
        self.assertEqual(kol_values.missing_labels(["PERSON_ID_NO", "PARTY_ADDRESS (không điền được)", "LA"]),
                         ["CCCD", "địa chỉ (không điền được - kiểm lại mẫu)", "<<LA>>"])
        self.assertTrue(kol_values.missing_is_creator(["BRAND", "PERSON_DOB"]))
        self.assertFalse(kol_values.missing_is_creator(["BRAND"]))


if __name__ == "__main__":
    unittest.main()
