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
MODS = ("kol_lookup", "kol_service", "kol_files", "kol_ai", "kol_acceptance", "kol_funding", "kol_verify",
        "kol_preview", "esign_hooks")


class _Throw(Exception):
    pass


class FakeDoc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def as_dict(self):
        return dict(self)

    def set(self, k, v):            # Document.set
        self[k] = v


def _fake_frappe(state):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.ValidationError = type("ValidationError", (Exception,), {})
    fk.new_doc = lambda dt_: FakeDoc(doctype=dt_)
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.get_doc = lambda *a, **k: FakeDoc()

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
        for m in MODS:
            sys.modules.pop(PKG + "." + m, None)
        cls.lookup = importlib.import_module(PKG + ".kol_lookup")
        cls.svc = importlib.import_module(PKG + ".kol_service")
        cls.files = importlib.import_module(PKG + ".kol_files")
        cls.ai = importlib.import_module(PKG + ".kol_ai")
        cls.funding = importlib.import_module(PKG + ".kol_funding")
        cls.lookup.brand_code = lambda brand: "FCV" if brand else ""

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for m in MODS:
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

    def test_ngay_ky_tu_tinh_chay_theo_lich_moi_ngay_tu_chon_thi_giu(self):
        # Lan truoc: lich 20/11, ngay ky TU TINH 19/11. Doi lich sang 15/12 ma khong dong vao o ngay
        # ky -> tinh lai 14/12 (truoc: dinh 19/11 vi coi la ngay nguoi dung chon - QC 12/11).
        self.state["stored"]["CR-9"] = {"air_dates": "20/11/2026", "contract_date": "2026-11-19",
                                        "creation": "2026-11-12 09:00:00"}
        doc = FakeDoc(name="CR-9", air_dates="15/12/2026", contract_date="2026-11-19", creation="2026-11-12")
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-14")
        # Nguoi dung sua tay sang 01/12 (khac ngay da luu) -> giu.
        doc = FakeDoc(name="CR-9", air_dates="15/12/2026", contract_date="2026-12-01", creation="2026-11-12")
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-01")
        # Nhap tu hom tao phieu (chua co lich, ngay ky = hom nay) roi moi nhap lich -> tinh theo lich.
        self.state["stored"]["CR-9"] = {"air_dates": "", "contract_date": "2026-11-12", "creation": "2026-11-12"}
        doc = FakeDoc(name="CR-9", air_dates="15/12/2026", contract_date="2026-11-12", creation="2026-11-12")
        self.svc.set_sign_date(doc)
        self.assertEqual(doc.contract_date, "2026-12-14")

    def test_xem_truoc_ngay_va_so_hd(self):
        old = self.svc.creator_row
        self.svc.creator_row = lambda n: {"ec_cr_type": "Cá nhân", "supplier_name": "Nguyễn Thị Phương"} if n else None
        try:
            r = self.svc.preview_dates("05,06/12/2026", None, "SUP-1", "FCV")
            self.assertEqual((r["dates"], r["sign_date"], r["contract_no"]),
                             (["05/12/2026", "06/12/2026"], "04/12/2026", "05122026/HDDV/ECENTRIC-NTP.FCV"))
            self.assertFalse(self.svc.preview_dates("05-06/12", None, None, None)["ok"])
            gaps = self.svc.creator_gaps("SUP-1")["labels"]
            self.assertIn("địa chỉ", gaps)
            self.assertIn("CCCD", gaps)
        finally:
            self.svc.creator_row = old

    def test_so_tien_dau_phay_van_khop_may_kiem(self):
        # Mau tool cu in "9,000,000": may kiem phai thay so tien (truoc: tach 9/000/000 -> "Loi").
        self.assertIn("9000000", self.ai.number_tokens("thực nhận 9,000,000 VNĐ"))
        checks = self.ai.data_checks("Số 05122026/HDDV/ECENTRIC-NTP.FCV · 9,000,000 VNĐ",
                                     {"payable_amount": 9_000_000, "contract_no": "05122026/HDDV/ECENTRIC-NTP.FCV"}, {})
        self.assertTrue(all(c["value_present"] for c in checks))

    def test_dntt_bat_buoc_so_va_kiem_quyen_so(self):
        f = self.funding
        old = f.kol_lookup.so_allowed
        try:
            with self.assertRaises(_Throw):
                f.funding_validate(FakeDoc(ec_sales_order=""), "a@ecentric.vn")
            f.kol_lookup.so_allowed = lambda u, so: (None, "SO %s không thuộc team" % so)
            with self.assertRaises(_Throw):
                f.funding_validate(FakeDoc(ec_sales_order="SO-X"), "a@ecentric.vn")
            f.kol_lookup.so_allowed = lambda u, so: ({"name": so}, None)
            f.funding_validate(FakeDoc(ec_sales_order="SO-1"), "a@ecentric.vn")
        finally:
            f.kol_lookup.so_allowed = old

    def test_dntt_khong_ghi_de_so_nguoi_lap_da_chon(self):
        f = self.funding
        olds = (f._doc, f.funding_can_use)
        f._doc = lambda n: FakeDoc(contract_type="KOL/KOC / Creator (EC)", sales_order="SO-CU", brand=None,
                                   creator_name="A")
        f.funding_can_use = lambda u, n: True
        try:
            pr = FakeDoc(ec_sales_order="SO-MOI", requested_by="a@ecentric.vn")
            f.fill_payment(pr, "CR-1")
            self.assertEqual(pr.ec_sales_order, "SO-MOI")
            pr = FakeDoc(requested_by="a@ecentric.vn")
            f.fill_payment(pr, "CR-1")
            self.assertEqual(pr.ec_sales_order, "SO-CU")         # phieu cu da gan SO: chi goi y
        finally:
            f._doc, f.funding_can_use = olds

    def test_mau_chon_tay_phai_hop_coc_va_nen_tang(self):
        m = self.lookup.template_mismatch
        t = {"is_active": 1, "kind": "Hợp đồng", "creator_type": "Cá nhân", "has_advance": 0, "platform": "Tất cả",
             "service_type": "Tất cả"}
        self.assertEqual(m(t, "Hợp đồng", "Cá nhân", False, "TikTok", "Video"), "")
        self.assertIn("cọc", m(t, "Hợp đồng", "Cá nhân", True, "TikTok", "Video"))
        self.assertIn("Shopee", m(t, "Hợp đồng", "Cá nhân", False, "Shopee", "Livestream"))
        self.assertIn("dịch vụ", m(t, "Hợp đồng", "Cá nhân", False, "TikTok", "Hoa hồng affiliate"))

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
        # Hoa hong affiliate: KHONG lay mau livestream / "Tat ca" (van ban sai), chi mau dung dich vu.
        self.assertIsNone(pick(H, "Cá nhân", "Hoa hồng affiliate", False, "TikTok"))
        self.state["get_all"]["EC Contract Template"].append(self._tpl("HD-CN-AFF", H, "Cá nhân", "Hoa hồng affiliate"))
        self.assertEqual(pick(H, "Cá nhân", "Hoa hồng affiliate", False, "TikTok"), "HD-CN-AFF")
        self.assertEqual(pick(H, "Cá nhân", "Livestream", False, "TikTok"), "HD-CN-LIVE")


    def test_chon_mau_khi_chua_chon_dich_vu_khong_loi(self):
        # QC2: service_type rong tung lam want.index() nem ValueError.
        self.state["get_all"]["EC Contract Template"] = [self._tpl("HD-CN-VIDEO", "Hợp đồng", "Cá nhân", "Video"),
                                                         self._tpl("HD-CN", "Hợp đồng", "Cá nhân")]
        self.assertEqual(self.lookup.pick_template("Hợp đồng", "Cá nhân", None, False, "TikTok"), "HD-CN")

    # ---------------------------------------------------------- PO 12/11 10:00
    def test_nguoi_duyet_xem_duoc_doanh_thu_so(self):
        f = self.funding
        self._patch(f.kol_lookup, is_finance=lambda u: u == "kt@ec")
        rows = {("AR-1", "duyet@ec")}
        self._patch(f.frappe.db, exists=lambda dt, flt=None: (flt or {}).get("approval_request") and
                    ((flt["approval_request"], flt["approver"]) in rows))
        pr = {"requested_by": "nv@ec", "approval_request": "AR-1"}
        self.assertEqual([f.funding_so_can_view(pr, u) for u in ("nv@ec", "kt@ec", "duyet@ec", "khac@ec")],
                         [True, True, True, False])
        self.assertFalse(f.funding_so_can_view({"requested_by": "nv@ec"}, "duyet@ec"))   # phieu nhap

    def _preview_setup(self, values, pii=True):
        from test_contract_kol_domain import make_docx
        pv = importlib.import_module(PKG + ".kol_preview")
        f, s = self.files, self.svc
        body = ('<w:p><w:r><w:t xml:space="preserve">Ông/Bà: &lt;&lt;PERSON_FULL_NAME&gt;&gt; '
                'CCCD &lt;&lt;PERSON_ID_NO&gt;&gt; STK &lt;&lt;BANK_ACCOUNT_NO&gt;&gt;</w:t></w:r></w:p>')
        saved = []
        self._patch(s, prepare_draft=lambda d: d.update(creator_type="Cá nhân"), apply_amounts=lambda d, strict=False: None,
                    assign_number=lambda d, c: d.update(contract_no="X/1"), ref_day=lambda d: dt.date(2026, 11, 12),
                    expected_bbnt_date=lambda d: None)
        self._patch(s.kol, validate_kol=lambda d, t, today=None: [])
        self._patch(pv, creator_row=lambda n: {"supplier_name": "A", "owner": "nguoi.tao@ec"},
                    _can_see_pii=lambda u, c: pii)
        self._patch(f, template_for=lambda d, k: "T1", file_bytes=lambda u: make_docx(body),
                    attach=lambda *a: saved.append(a), _values=lambda d, c, b: dict(values))
        self._patch(pv.frappe, new_doc=lambda dt_: FakeDoc(doctype=dt_),
                    get_doc=lambda *a: FakeDoc(name="T1", template_name="HĐ cá nhân", template_file="/f.docx"))
        return pv, saved

    def _xml(self, r):
        import base64
        import io
        import zipfile
        return zipfile.ZipFile(io.BytesIO(base64.b64decode(r["docx"]))).read("word/document.xml").decode()

    def test_xem_truoc_hop_dong_to_mau_khong_luu_gi(self):
        pv, saved = self._preview_setup({"PERSON_FULL_NAME": "Nguyễn A", "PERSON_ID_NO": "", "BANK_ACCOUNT_NO": "0011"})
        s = self.svc
        r = pv.preview_contract({"contract_type": s.kol.KOL_CONTRACT_TYPE, "request_type": s.kol.TEMPLATE_EC,
                                 "creator": "SUP-1", "requested_by": "hacker@x"}, None, "a@ecentric.vn")
        self.assertTrue(r["ok"], r)
        xml = self._xml(r)
        self.assertIn('<w:highlight w:val="yellow"/></w:rPr><w:t xml:space="preserve">Nguyễn A', xml)
        self.assertIn("[Thiếu: CCCD]", xml)
        self.assertIn("0011", xml)                                    # nguoi xem duoc PII: thay so that
        self.assertIn("CCCD", r["missing_labels"][0])
        self.assertEqual(saved, [])                                   # khong dinh kem / luu gi
        r = pv.preview_contract({"contract_type": s.kol.KOL_CONTRACT_TYPE, "request_type": s.kol.TEMPLATE_PARTNER},
                                None, "a@ecentric.vn")
        self.assertFalse(r["ok"])

    def test_xem_truoc_an_pii_khi_khong_co_quyen(self):
        pv, _s = self._preview_setup({"PERSON_FULL_NAME": "Nguyễn A", "PERSON_ID_NO": "079123456789",
                                      "BANK_ACCOUNT_NO": "0011"}, pii=False)
        r = pv.preview_contract({"contract_type": self.svc.kol.KOL_CONTRACT_TYPE,
                                 "request_type": self.svc.kol.TEMPLATE_EC, "creator": "SUP-1"}, None, "x@ec")
        xml = self._xml(r)
        self.assertNotIn("079123456789", xml)
        self.assertNotIn("0011", xml)
        self.assertIn(pv.MASK, xml)
        self.assertIn("Nguyễn A", xml)                                # ten khong phai PII an

    def test_xem_truoc_mau_hong_va_phieu_khong_co(self):
        pv, _s = self._preview_setup({"PERSON_FULL_NAME": "A"})
        logged = []
        self._patch(self.files, file_bytes=lambda u: b"khong phai zip")
        self._patch(pv.frappe, log_error=lambda *a, **k: logged.append(a), get_traceback=lambda: "tb")
        r = pv.preview_contract({"contract_type": self.svc.kol.KOL_CONTRACT_TYPE,
                                 "request_type": self.svc.kol.TEMPLATE_EC, "creator": "SUP-1"}, None, "a@ec")
        self.assertFalse(r["ok"])
        self.assertIn("lỗi định dạng", r["error"])
        self.assertTrue(logged)
        self._patch(pv.frappe.db, exists=lambda *a, **k: False)
        r = pv.preview_contract({}, "CR-XOA", "a@ec")
        self.assertFalse(r["ok"])
        self.assertIn("Không tìm thấy", r["error"])
        self._patch(pv.frappe.db, exists=lambda *a, **k: True)
        self._patch(pv.frappe, get_doc=lambda *a: FakeDoc(name="CR-9", requested_by="b@ecentric.vn"))
        self._patch(pv, can_manage=lambda d, u: False)
        with self.assertRaises(_Throw):                                # phieu nguoi khac: khong xem truoc
            pv.preview_contract({}, "CR-9", "a@ecentric.vn")
        self.assertEqual([pv.parse_fields(x) for x in ('{"a": 1}', "[1]", "{hong", None, {"b": 2})],
                         [{"a": 1}, {}, {}, {}, {"b": 2}])

    def test_bang_tinh_dot_phu_het_hop_dong_lay_so_da_luu(self):
        acc = importlib.import_module(PKG + ".kol_acceptance")
        k = self.svc.kol
        a = k.compute_amounts("Cá nhân", k.GROSS_BEFORE_PIT, 2621905, 10)
        doc = FakeDoc(creator_type="Cá nhân", amount_type=k.GROSS_BEFORE_PIT, gross_amount=a["gross"],
                      pit_amount=a["pit"], vat_amount=0, payable_amount=a["payable"], pit_rate=10,
                      acceptances=[1])
        rows = acc._round_calc(doc, FakeDoc(amount=a["payable"]))
        amounts = [r["amount"] for r in rows]
        self.assertIn(2621905, amounts)                               # = so in tren BBNT (so hop dong)
        self.assertIn(262191, amounts)

    def test_nen_tang_ky_so_bao_ky_du(self):
        """Chot 12/11 voi chat Ky so: cong ky du -> goi esign_hooks.on_signed, phia Hop dong tu ghi."""
        h = importlib.import_module(PKG + ".esign_hooks")
        k = self.svc.kol
        comments = []
        doc = FakeDoc(name="CR-1", contract_type="Purchase / Mua vào (EC)", signing_status=k.SIGN_PENDING)
        doc.save = lambda ignore_permissions=False: None
        doc.add_comment = lambda kind, text: comments.append(text)
        self._patch(h.frappe, get_doc=lambda dt_, n: doc)
        r = h.on_signed("CR-1", "contract", "/private/files/HD_ky.pdf")
        self.assertEqual((r["changed"], doc.signing_status, doc.signed_file), (True, k.SIGN_DONE, "/private/files/HD_ky.pdf"))
        self.assertFalse(h.on_signed("CR-1", "contract", "/private/files/HD_ky.pdf")["changed"])   # goi lai: khong doi
        # BBNT dot r1 -> finish_round (han thanh toan, may kiem) voi nguon "Ky so (cong)".
        acc = importlib.import_module(PKG + ".kol_acceptance")
        row = FakeDoc(name="r1", idx=1, status=k.BBNT_SENT)
        doc.acceptances = [row]
        seen = []
        self._patch(acc, finish_round=lambda d, r, f, w, by: (seen.append((r.name, f, by)), r.update(status=k.BBNT_DONE))[0] and [])
        r = h.on_signed("CR-1", "bbnt:r1", "/private/files/BBNT_ky.pdf")
        self.assertEqual(seen, [("r1", "/private/files/BBNT_ky.pdf", h.ESIGN_ACTOR)])
        self.assertFalse(h.on_signed("CR-1", "bbnt:r1", "/private/files/BBNT_ky.pdf")["changed"])
        for bad in (("CR-1", "bbnt:r9", "/a.pdf"), ("CR-1", "khac", "/a.pdf"), ("CR-1", "contract", "/a.docx")):
            with self.assertRaises(ValueError):
                h.on_signed(*bad)

    def test_finish_round_nguon_cong_khong_ghi_link_user(self):
        acc = importlib.import_module(PKG + ".kol_acceptance")
        k = self.svc.kol
        comments = []
        doc = FakeDoc(name="CR-1", payment_term_days=30, creator_type="Cá nhân", platform="TikTok")
        doc.save = lambda ignore_permissions=False: None
        doc.add_comment = lambda kind, text: comments.append(text)
        verify = importlib.import_module(PKG + ".kol_verify")
        self._patch(verify, apply_acceptance_check=lambda d, r: r.update(status=k.BBNT_DONE) or [])
        self._patch(acc.kol_lookup, holidays=lambda: set())
        row = FakeDoc(name="r1", idx=1, status=k.BBNT_SENT)
        acc.finish_round(doc, row, "/b.pdf", dt.datetime(2026, 11, 12, 9), "Ký số (cổng)")
        self.assertIsNone(row.completed_by)
        self.assertEqual(row.due_date, dt.date(2026, 12, 14))            # 12/11 + 30 = 12/12 (T7) -> 14/12
        self.assertIn("Ký số (cổng)", comments[0])

    # ---------------------------------------------------------- QC vong 3
    def test_hoan_tat_bbnt_phai_qua_buoc_gui_ky(self):
        acc = importlib.import_module(PKG + ".kol_acceptance")
        row = FakeDoc(name="r1", idx=1, status=acc.kol.BBNT_DRAFT)
        self._patch(acc, _load=lambda n, u: FakeDoc(), _row=lambda d, r: row)
        for st, word in ((acc.kol.BBNT_DRAFT, "Đánh dấu đã gửi ký"), (acc.kol.BBNT_REVIEW, "Kế toán")):
            row.status = st
            with self.assertRaises(_Throw) as cm:
                acc.complete_acceptance("CR-1", "a@ecentric.vn", "r1", "/s.pdf")
            self.assertIn(word, str(cm.exception))

    def test_ngay_nghiem_thu_khong_truoc_ngay_ky_khong_o_tuong_lai(self):
        acc = importlib.import_module(PKG + ".kol_acceptance")
        doc = FakeDoc(contract_date="2026-11-05")
        self.assertEqual(acc._check_acceptance_date(doc, "2026-11-10"), "2026-11-10")
        for bad in ("2026-11-01", "2026-11-13", "10/11/2026"):
            with self.assertRaises(_Throw):
                acc._check_acceptance_date(doc, bad)
        with self.assertRaises(_Throw) as cm:
            acc._check_acceptance_date(doc, "2026-11-01")
        self.assertIn("không cần trùng ngày live", str(cm.exception))
        # Live lam som hon lich, hop dong ghi ngay ky sau hom nay: noi ro doi / phu luc (PO 12/11).
        with self.assertRaises(_Throw) as cm:
            acc._check_acceptance_date(FakeDoc(contract_date="2026-11-20"), "2026-11-10")
        self.assertIn("phụ lục", str(cm.exception))

    def test_xem_truoc_khong_doc_phieu_nguoi_khac(self):
        self.state["stored"]["CR-X"] = {"requested_by": "b@ecentric.vn", "creation": "2025-01-10 09:00:00"}
        self._patch(self.svc.kol_lookup, is_finance=lambda u: False)
        # Phieu cua nguoi khac tao 01/2025: neu dung moc cua no thi "05/01" ra 2025; bo qua -> moc hom nay.
        r = self.svc.preview_dates("05/01", None, None, None, "CR-X", "a@ecentric.vn")
        self.assertEqual(r["dates"], ["05/01/2027"])
        r = self.svc.preview_dates("05/01", None, None, None, "CR-X", "b@ecentric.vn")
        self.assertEqual(r["dates"], ["05/01/2025"])
        r = self.svc.preview_dates("05/12/2026", "12-11-2026", None, None)       # ngay ky sai dang: khong 500
        self.assertTrue(r["ok"])

    def test_chua_co_mau_bbnt_khong_khuyen_dung_mau_creator(self):
        self.state["get_all"]["EC Contract Template"] = []
        with self.assertRaises(_Throw) as cm:
            self.files.template_for(FakeDoc(creator_type="Cá nhân", service_type="Video", platform="TikTok"),
                                    self.files.KIND_BBNT)
        self.assertNotIn("mẫu của creator", str(cm.exception))
        self.assertIn("mẫu BBNT", str(cm.exception))

    # ---------------------------------------------------------- QC vong 2
    def _patch(self, obj, **kw):
        olds = {k: getattr(obj, k) for k in kw}
        for k, v in kw.items():
            setattr(obj, k, v)
        self.addCleanup(lambda: [setattr(obj, k, v) for k, v in olds.items()])

    def test_doi_sang_mau_creator_xoa_ket_qua_dien_mau_ec(self):
        s = self.svc
        self._patch(s, creator_row=lambda n: {"ec_cr_type": "Cá nhân", "supplier_name": "A"},
                    prepare_draft=lambda d: None, apply_amounts=lambda d, strict=False: None,
                    assign_number=lambda d, c: None)
        self._patch(s.kol, validate_kol=lambda d, t, today=None: [])
        doc = FakeDoc(name="CR-5", creator="SUP-1", request_type=s.kol.TEMPLATE_PARTNER, request_attachment="/f.pdf",
                      missing_placeholders="CONTRACT_NO", contract_fingerprint="x", generated_template="T")
        s.validate_submit(doc)            # khong nem "con thieu" vi ket qua mau EC cu
        self.assertEqual((doc.missing_placeholders, doc.contract_fingerprint, doc.generated_template),
                         (None, None, None))
        self.assertIsNone(doc.revenue_warning)

    def test_gui_bbnt_sinh_lai_tep_theo_du_lieu_moi(self):
        acc = importlib.import_module(PKG + ".kol_acceptance")
        row = FakeDoc(idx=1, status=acc.kol.BBNT_DRAFT, bbnt_file="/old.docx")
        saved, dropped = [], []
        doc = FakeDoc(contract_no="X/1", creator="SUP-1")
        doc.save = lambda ignore_permissions=False: saved.append(1)
        self._patch(acc, _load=lambda n, u: doc, _row=lambda d, r: row, creator_row=lambda n: {"ec_cr_type": "Cá nhân"})
        self._patch(self.files, acceptance_content=lambda d, r, c, tpl=None: (b"new", []),
                    attach=lambda d, fn, c: "/new.docx",
                    _drop_generated=lambda d, url, prefix="", keep_if_sent=True: dropped.append(url))
        comments = []
        doc.add_comment = lambda kind, text: comments.append(text)
        # Noi dung DOI (URL moi): KHONG danh dau da gui - ban creator dang cam khong phai ban nay; giu
        # tep cu lam vet, ghi chu (QC3).
        r = acc.send_acceptance("CR-1", "a@ecentric.vn", "r1")
        self.assertEqual((row.bbnt_file, row.status, dropped, r.get("regenerated")),
                         ("/new.docx", acc.kol.BBNT_DRAFT, [], True))
        self.assertTrue(comments and "/old.docx" in comments[0])
        # Bam lai (noi dung khong doi -> cung URL): moi danh dau da gui.
        r = acc.send_acceptance("CR-1", "a@ecentric.vn", "r1")
        self.assertEqual((row.status, r.get("regenerated")), (acc.kol.BBNT_SENT, None))
        # Con thieu (creator chua co CCCD): chan, bao nhan tieng Viet, khong doi tep.
        row.status, row.bbnt_file = acc.kol.BBNT_DRAFT, "/old.docx"
        self._patch(self.files, acceptance_content=lambda d, r, c, tpl=None: (b"x", ["PERSON_ID_NO"]))
        with self.assertRaises(_Throw) as cm:
            acc.send_acceptance("CR-1", "a@ecentric.vn", "r1")
        self.assertNotIn("PERSON_ID_NO", str(cm.exception))
        self.assertEqual(row.bbnt_file, "/old.docx")

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
                         ["CCCD", "địa chỉ (mẫu bị lỗi định dạng ở chỗ này - báo Kế toán sửa mẫu)", "<<LA>>"])
        self.assertTrue(kol_values.missing_is_creator(["BRAND", "PERSON_DOB"]))
        self.assertFalse(kol_values.missing_is_creator(["BRAND"]))


if __name__ == "__main__":
    unittest.main()
