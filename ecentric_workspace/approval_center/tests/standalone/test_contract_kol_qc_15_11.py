# Copyright (c) 2026, eCentric and contributors
"""QC dem 15/11/2026 (4 vong agent): khoa cac loi tien / ky da sua. Frappe gia toi thieu nhu cac test KOL khac."""
import datetime as dt
import sys
import types


class Throw(Exception):
    pass


class Row(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def as_dict(self):
        return dict(self)


class Doc(Row):
    _n = 0

    def append(self, field, value):
        Doc._n += 1
        r = Row(value, name="row%d" % Doc._n, idx=len(self.get(field) or []) + 1)
        self.setdefault(field, []).append(r)
        return r

    def remove(self, r):
        for k, v in self.items():
            if isinstance(v, list) and r in v:
                v.remove(r)
                for i, x in enumerate(v):
                    x["idx"] = i + 1

    def save(self, **kw):
        STATE["saves"] += 1

    def add_comment(self, kind, msg):
        STATE["comments"].append(msg)

    def set(self, k, v):
        self[k] = v


STATE = {"docs": {}, "values": {}, "roles": {}, "get_all": {}, "saves": 0, "comments": [], "exists": set()}


def install(today="2026-11-15", user="a@ec"):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Throw,), {})
    fk.ValidationError = type("ValidationError", (Throw,), {})

    def throw(msg, exc=None):
        raise (exc or Throw)(msg)
    fk.throw = throw
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.session = types.SimpleNamespace(user=user)
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.get_doc = lambda dt_, name=None: STATE["docs"][(dt_, name)]
    fk.get_roles = lambda u=None: list(STATE["roles"].get(u or fk.session.user, []))

    def get_value(dt_, name, field=None, as_dict=False, **kw):
        key = (dt_, name if not isinstance(name, dict) else tuple(sorted(name.items())))
        v = STATE["values"].get(key)
        if callable(v):
            return v(field, as_dict)
        if v is None and (dt_, name) in STATE["docs"] and isinstance(field, str):
            return STATE["docs"][(dt_, name)].get(field)
        return v
    def exists(dt_, name=None):
        if isinstance(name, dict):
            return (dt_, tuple(sorted(name.items()))) in STATE["exists"]
        return (dt_, name) in STATE["exists"] or (dt_, name) in STATE["docs"]
    fk.db = types.SimpleNamespace(get_value=get_value, exists=exists, set_value=lambda *a, **k: None)

    def get_all(doctype, filters=None, **kw):
        f = STATE["get_all"].get(doctype)
        return f(filters, kw) if callable(f) else list(f or [])
    fk.get_all = get_all
    fk.get_cached_value = lambda *a, **k: None
    fk.defaults = types.SimpleNamespace(get_global_default=lambda k: None)
    fk._attrs = {}
    def get_attr(path):
        if path in fk._attrs:
            return fk._attrs[path]
        mod, _, fn = path.rpartition(".")
        __import__(mod)
        return getattr(sys.modules[mod], fn)
    fk.get_attr = get_attr
    utils = types.ModuleType("frappe.utils")
    utils.flt = lambda v, p=None: float(v or 0)
    utils.nowdate = lambda: today
    utils.today = lambda: today
    utils.now_datetime = lambda: dt.datetime.fromisoformat(today + " 10:00:00")
    utils.getdate = lambda v: dt.date.fromisoformat(str(v)[:10])
    utils.get_datetime = lambda v=None: dt.datetime.fromisoformat(str(v)) if v else utils.now_datetime()
    utils.cint = lambda v: int(float(v or 0))
    utils.cstr = lambda v: "" if v is None else str(v)
    utils.now = lambda: today + " 10:00:00"
    fk.utils = utils
    sys.modules["frappe"], sys.modules["frappe.utils"] = fk, utils
    return fk


import importlib
import unittest

CR = "EC Contract Review Request"
P = "ecentric_workspace.approval_center.features.contract_review.application."


def _fresh(user="fin@ec"):
    STATE.update({"docs": {}, "values": {}, "roles": {}, "get_all": {}, "saves": 0, "comments": [], "exists": set()})
    install(user=user)
    for m in [k for k in sys.modules if k.startswith("ecentric_workspace.approval_center.features.contract_review.application")]:
        sys.modules.pop(m)
    return (importlib.import_module(P + "kol_service"), importlib.import_module(P + "kol_verify"),
            importlib.import_module(P + "kol_acceptance"), importlib.import_module(P + "kol_files"))


def _doc(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type="KOL/KOC / Creator (EC)", requested_by="fin@ec", owner="fin@ec",
            approval_request="AR-1", contract_no="15112026/HDDV/ECENTRIC-NTP.FCV", signing_status="Chưa ký",
            payable_amount=10_000_000, advance_amount=0, gross_amount=11_111_111, creator_type="Cá nhân",
            contract_date="2026-11-10", acceptances=[])
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
    return d


class TuXacNhan(unittest.TestCase):
    """C2 / B-08 / D11: nguoi lap / nguoi tai ban ky (ke ca Ke toan, SM) khong tu xac nhan."""

    def test_nguoi_lap_la_ke_toan_khong_tu_xac_nhan_hop_dong(self):
        svc, ver, _acc, _f = _fresh("fin@ec")
        STATE["roles"]["fin@ec"] = ["EC Finance"]
        d = _doc(signing_status="Chờ kiểm tra", signed_marked_by="fin@ec")
        with self.assertRaises(Throw):
            ver.verify_contract("CR-1", "fin@ec", True)
        self.assertEqual(d.signing_status, "Chờ kiểm tra")

    def test_ke_toan_khac_xac_nhan_duoc(self):
        svc, ver, _acc, _f = _fresh("kt2@ec")
        STATE["roles"]["kt2@ec"] = ["EC Finance"]
        d = _doc(signing_status="Chờ kiểm tra", signed_marked_by="fin@ec")
        ver.verify_contract("CR-1", "kt2@ec", True)
        self.assertEqual(d.signing_status, "Đã ký đủ")

    def test_bbnt_nguoi_hoan_tat_khong_tu_xac_nhan(self):
        svc, ver, _acc, _f = _fresh("kt2@ec")
        STATE["roles"]["kt2@ec"] = ["EC Finance"]
        d = _doc(signing_status="Đã ký đủ")
        d.acceptances = [Row(name="r1", idx=1, status="Chờ kiểm tra", completed_by="kt2@ec", amount=1)]
        with self.assertRaises(Throw):
            ver.verify_acceptance("CR-1", "kt2@ec", "r1", True)


class BbntTrungTep(unittest.TestCase):
    """C3: tep ban ky cua dot truoc dung lai cho dot sau -> chuyen Ke toan (khong tu hoan tat)."""

    def test_trung_noi_dung_dot_truoc(self):
        _svc, ver, _acc, _f = _fresh()
        d = _doc(signing_status="Đã ký đủ")
        r1 = Row(name="r1", idx=1, status="Hoàn tất", signed_file="/private/files/a.pdf", amount=5_000_000)
        r2 = Row(name="r2", idx=2, status="Đã gửi ký", signed_file="/private/files/b.pdf", amount=5_000_000)
        d.acceptances = [r1, r2]
        ver.doc_file_bytes = lambda doc, url: b"%PDF-1.7 cung noi dung"
        ver.check = lambda doc, url, amount=None: []          # gia su may kiem khac deu dat
        ver.apply_acceptance_check(d, r2)
        self.assertEqual(r2.status, "Chờ kiểm tra")
        self.assertIn("đợt 1", r2.check_note)


class SoTienDot(unittest.TestCase):
    """C7: so tien dot phai la dong chan; nan / 0 / am bi chan."""

    def test_so_le_nan_am(self):
        _svc, _ver, acc, _f = _fresh()
        _doc(signing_status="Đã ký đủ")
        for bad in (333333.5, float("nan"), 0, -5):
            with self.assertRaises(Throw):
                acc.add_acceptance("CR-1", "fin@ec", "Dot", "2026-11-12", bad)


# ----------------------------------------------------------------------------- mien (khong frappe)
from ecentric_workspace.approval_center.features.contract_review.domain import (  # noqa: E402
    docx_fill, docx_safe, kol, kol_texts as T, kol_values as V)
from ecentric_workspace.approval_center.shared.creators import domain as CD  # noqa: E402


class SoHopDong(unittest.TestCase):
    """A3 / A4: ma tay cua ca nhan va ma brand khong duoc mang ky tu la vao so HD."""

    def test_ma_ca_nhan_ky_tu_la_thi_suy_tu_ten(self):
        self.assertEqual(T.party_code("Cá nhân", "Nguyễn Văn A", "A/B"), "NVA")
        self.assertEqual(T.party_code("Cá nhân", "Nguyễn Văn A", "N.V.A"), "NVA")
        self.assertEqual(T.party_code("Cá nhân", "Nguyễn Văn A", "đức"), "DUC")
        self.assertEqual(T.party_code("Cá nhân", "Nguyễn Văn A", " ab-1 "), "AB-1")

    def test_ma_brand_bo_dau_cach_va_bao_ky_tu_la(self):
        self.assertTrue(kol.contract_number("2026-12-05", "DL", " frl vn ").endswith(".FRLVN"))
        with self.assertRaises(ValueError):
            kol.contract_number("2026-12-05", "DL", "A.B")


class NgayVaKenh(unittest.TestCase):
    def test_ngay_ghi_du_nam_cach_xa_khong_bao_ghi_ro_nam(self):
        # A6: van chan (go nham nam hay gap) nhung khong bao "ghi ro nam" khi nguoi dung da ghi.
        with self.assertRaises(ValueError) as cm:
            T.parse_service_dates("05/12/2026, 05/07/2027", dt.date(2026, 11, 15))
        self.assertNotIn("Ghi rõ năm", str(cm.exception))
        self.assertIn("Kiểm lại năm", str(cm.exception))

    def test_id_kenh_luu_dang_url_khong_in_link_hong(self):
        # A7
        v = V.contract_values({"creator_type": "Cá nhân", "service_type": "Livestream", "platform": "TikTok",
                               "brand": "X"}, {"supplier_name": "A", "ec_cr_tiktok_id": "https://www.tiktok.com/@AbC?x=1"},
                              "X", dt.date(2026, 12, 4), [dt.date(2026, 12, 5)])
        self.assertEqual(v["CHANNEL_URL"], "https://www.tiktok.com/@AbC")
        self.assertEqual(v["TIKTOK_ID_DISPLAY"], "AbC")
        self.assertEqual(CD._handle("https://www.tiktok.com/@AbC"), "abc")      # so trung van ha chu

    def test_thieu_ngan_hang_thi_rong_cho_chot_thieu_bat(self):
        # A8
        self.assertEqual(T.bank_branch("", "Hà Nội"), "")
        self.assertEqual(T.bank_branch("ACB", "Hà Nội"), "ACB - CN Hà Nội")

    def test_mst_chi_nhanh_in_co_gach(self):
        # A9
        self.assertEqual(T.tax_id_text("0123456789001"), "0123456789-001")
        self.assertEqual(T.tax_id_text("0123456789"), "0123456789")

    def test_ky_tu_cam_trong_xml_bi_bo(self):
        # A17
        self.assertEqual(docx_fill._CTRL.sub("", "A￾B￿C\ud800D"), "ABCD")


class LuatMauEc(unittest.TestCase):
    def _doc(self, **kw):
        d = {"brand": "X", "creator": "C", "service_type": "Livestream", "payment_schedule": kol.PAYMENT_SCHEDULES[0],
             "amount_type": kol.NET_AFTER_PIT, "request_type": kol.TEMPLATE_EC, "platform": "TikTok",
             "air_dates": "05/12/2026", "quantity": 1}
        d.update(kw)
        return d

    def test_mau_ec_bat_chon_nen_tang(self):
        # A18: bo trong thi mau van in "TikTok"
        errs = kol.validate_kol(self._doc(platform=""), "Cá nhân", dt.date(2026, 11, 15))
        self.assertTrue(any("nền tảng" in e for e in errs))
        self.assertEqual(kol.validate_kol(self._doc(), "Cá nhân", dt.date(2026, 11, 15)), [])

    def test_so_buoi_am_bi_chan(self):
        # A19
        errs = kol.validate_kol(self._doc(quantity=-1), "Cá nhân", dt.date(2026, 11, 15))
        self.assertTrue(any("không được âm" in e for e in errs))


class DotCuoiKhopHopDong(unittest.TestCase):
    """A2 / C4: cong cac BBNT nhieu dot phai ra dung so cua hop dong (truoc lech 1d)."""

    def _sum(self, ct, typ, amt, rate, split, sched=None, pct=None):
        a = kol.compute_amounts(ct, typ, amt, rate if ct == "Cá nhân" else None, rate if ct == "Công ty" else None)
        adv = kol.advance_amount(a, ct, sched, pct) if sched else 0
        doc = {"creator_type": ct, "payable_amount": a["payable"], "gross_amount": a["gross"], "vat_amount": a["vat"],
               "advance_amount": adv, "pit_rate": rate if ct == "Cá nhân" else None,
               "vat_rate": rate if ct == "Công ty" else None}
        doc["acceptances"] = [{"idx": i + 1, "amount": x} for i, x in enumerate(split(a["payable"] - adv))]
        tot = dict.fromkeys(V._MONEY_KEYS, 0)
        for r in doc["acceptances"]:
            m = V._closing_adjust(doc, r, V.round_money(ct, r["amount"], doc["pit_rate"], doc["vat_rate"], doc))
            for k in tot:
                tot[k] += m[k]
        return a, adv, tot

    def test_ca_nhan_hai_dot(self):
        a, _adv, t = self._sum("Cá nhân", kol.NET_AFTER_PIT, 1_000_003, 10, lambda r: [500_001, r - 500_001])
        self.assertEqual((t["gross"], t["net"]), (a["gross"], a["payable"]))

    def test_cong_ty_ba_dot(self):
        a, _adv, t = self._sum("Công ty", kol.BEFORE_VAT, 10_000_001, 8, lambda r: [3_600_000, 3_600_000, r - 7_200_000])
        self.assertEqual((t["pre_vat"], t["vat"]), (a["gross"], a["vat"]))

    def test_cong_ty_coc_ba_dot(self):
        a, adv, t = self._sum("Công ty", kol.BEFORE_VAT, 10_000_003, 8,
                              lambda r: [2_600_000, 2_600_000, r - 5_200_000], kol.PAY_ADVANCE, 30)
        self.assertEqual((t["pre_vat"] + adv, t["vat"]), (a["gross"], a["vat"]))

    def test_dot_chua_phai_cuoi_giu_cach_tinh_thuong(self):
        doc = {"creator_type": "Cá nhân", "payable_amount": 1_000_003, "gross_amount": 1_111_114, "advance_amount": 0,
               "acceptances": [{"idx": 1, "amount": 500_001}, {"idx": 2, "amount": 100}]}
        m = V.round_money("Cá nhân", 100, 10, None, doc)
        self.assertEqual(V._closing_adjust(doc, doc["acceptances"][1], m), m)


def _docx(document_xml, rels_xml):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/_rels/document.xml.rels", rels_xml)
    return buf.getvalue()


class DocxSafe(unittest.TestCase):
    """D7 / A16: 5 kieu lot cua ban regex cu."""

    def test_nam_kieu_lot_deu_bi_chan(self):
        import io
        import zipfile
        doc = ('<w:document xmlns:w="w" xmlns:x="w"><w:body>'
               '<w:r><x:sym x:char="&lt;img onerror=alert(1)&gt;"/></w:r>'
               '<w:r><w:sym w:font="x>y" w:char="&lt;svg onload=alert(2)&gt;"/></w:r>'
               '<w:r><w:sym w:font="Symbol" w:char="F0B7"/></w:r></w:body></w:document>')
        rels = ("<Relationships>"
                "<Relationship Id='r1' Target='javascript:alert(3)' TargetMode='External'/>"
                '<Relationship Id="r2" Target="javascript:alert(4)" TargetMode = "External"/>'
                '<Relationship Id="r3" Target="javascript:alert(5)" TargetMode="External"></Relationship>'
                '<Relationship Id="r4" Target="https://ok.vn" TargetMode="External"/>'
                '<Relationship Id="r5" Target="media/a.png"/></Relationships>')
        out = zipfile.ZipFile(io.BytesIO(docx_safe.sanitize_for_viewer(_docx(doc, rels))))
        d = out.read("word/document.xml").decode()
        r = out.read("word/_rels/document.xml.rels").decode()
        for bad in ("alert(1)", "alert(2)"):
            self.assertNotIn(bad, d)
        self.assertIn('w:char="F0B7"', d)                  # ky hieu hop le giu nguyen
        self.assertNotIn("javascript:", r)
        self.assertIn("https://ok.vn", r)
        self.assertIn("media/a.png", r)


# ----------------------------------------------------------------------------- ung dung (frappe gia)
class NguoiKyPhiaCreator(unittest.TestCase):
    """B-04 / B-05 / A13."""

    def setUp(self):
        self.svc = _fresh("a@ec")[0]

    def test_thieu_email_hoac_email_noi_bo_bi_chan(self):
        ef = sys.modules["ecentric_workspace.approval_center.features.contract_review.domain.esign_flow"]
        flow = next(iter(ef.WITH_PARTNER))
        d = Doc(esign_flow=flow, partner_signer_name="Creator A", partner_signer_email="")
        self.assertTrue(self.svc.partner_signer_errors(d))
        STATE["exists"].add(("User", (("name", "nv@ecentric.vn"), ("user_type", "System User"))))
        d.partner_signer_email = "NV@ecentric.vn"
        self.assertIn("nội bộ", self.svc.partner_signer_errors(d)[0])
        d.partner_signer_email = "creator@gmail.com"
        self.assertEqual(self.svc.partner_signer_errors(d), [])
        self.assertEqual(self.svc.partner_signer_errors(Doc(esign_flow="")), [])     # khong ky tren cong

    def test_doi_creator_xoa_nguoi_ky_cu_giu_o_vua_sua(self):
        STATE["values"][(CR, "CR-1")] = lambda f, d: Row(creator="CR-A", partner_signer_name="A",
                                                         partner_signer_email="a@gmail.com", partner_signer_phone="0901")
        d = Doc(doctype=CR, name="CR-1", creator="CR-B", partner_signer_name="A",
                partner_signer_email="b-moi@gmail.com", partner_signer_phone="0901")
        d.is_new = lambda: False
        self.svc._reset_partner_on_creator_change(d)
        self.assertIsNone(d.partner_signer_name)
        self.assertIsNone(d.partner_signer_phone)
        self.assertEqual(d.partner_signer_email, "b-moi@gmail.com")

    def test_email_nguoi_ky_nam_trong_chu_ky_duyet(self):
        svc_mod = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
        sys.modules[svc_mod.__name__] = svc_mod
        import ecentric_workspace.approval_center.shared.workflow as wf
        wf.transitions = svc_mod
        service = importlib.import_module(P + "service")
        d = Doc(contract_type=kol.KOL_CONTRACT_TYPE, partner_signer_email="a@gmail.com")
        before = service._signature(d)
        d.partner_signer_email = "nv@ecentric.vn"
        self.assertNotEqual(service._signature(d), before)


class GuiLaiChayLaiChot(unittest.TestCase):
    """B-02: gui lai sau 'Can bo sung' chay lai chot cua luc gui."""

    def test_xoa_quy_trinh_ky_va_ly_do_khi_bo_sung_bi_chan(self):
        _fresh("a@ec")
        calls = []
        eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
        eng.resubmit = lambda *a, **k: calls.append(a) or {"esign": {"x": 1}}
        sys.modules[eng.__name__] = eng
        import ecentric_workspace.approval_center.shared.workflow as wf
        wf.transitions = eng
        sys.modules.pop(P + "service", None)
        service = importlib.import_module(P + "service")
        service._soi_guong_sharepoint = lambda n: None
        service._guard_resubmit_needs_ceo = lambda d: None
        d = Doc(doctype=CR, name="CR-9", approval_request="AR-9", request_title="HĐ mua", request_kind="New",
                contract_type="Purchase / Mua vào (EC)", request_type="Template from partner / Mẫu theo khung đối tác",
                brand="", justification="", contract_value=5, request_details="x", esign_flow="")
        STATE["docs"][(CR, "CR-9")] = d
        with self.assertRaises(Throw):
            service.resubmit("CR-9")
        self.assertEqual(calls, [])
        d.update(brand="FCV", justification="Mua", esign_flow=sys.modules[
            "ecentric_workspace.approval_center.features.contract_review.domain.esign_flow"].PARTNER_SIGNED)
        res = service.resubmit("CR-9")
        self.assertEqual(len(calls), 1)
        self.assertEqual(res["esign"], {"x": 1})            # B-12: khong bo mat ket qua ky so


class TepBanKy(unittest.TestCase):
    """D5: chi nhan tep rieng tu, so ca doctype. B-06: hook 'signed' chi nhan tep da gan phieu."""

    def test_tep_cong_khai_hoac_gan_doctype_khac_bi_chan(self):
        _svc, _v, _a, files = _fresh("a@ec")
        d = _doc()
        with self.assertRaises(Throw):
            files.claim_upload(d, "/files/ban_ky.pdf", "a@ec")
        STATE["get_all"]["File"] = [Row(name="F1", owner="a@ec", attached_to_doctype="EC Payment Request",
                                        attached_to_name="CR-1")]
        with self.assertRaises(Throw):
            files.claim_upload(d, "/private/files/ban_ky.pdf", "a@ec")
        STATE["get_all"]["File"] = [Row(name="F1", owner="a@ec", attached_to_doctype=None, attached_to_name=None)]
        self.assertEqual(files.claim_upload(d, "/private/files/ban_ky.pdf", "a@ec"), "/private/files/ban_ky.pdf")

    def test_hook_signed_tu_choi_ban_chua_ky_va_tep_chua_gan(self):
        _fresh("a@ec")
        hooks = importlib.import_module(P + "esign_hooks")
        d = _doc(contract_type="Purchase / Mua vào (EC)", request_attachment="/private/files/hd.pdf")
        with self.assertRaises(ValueError):
            hooks._check_signed_file(d, "/private/files/hd.pdf")
        with self.assertRaises(ValueError):
            hooks._check_signed_file(d, "/private/files/la.pdf")
        STATE["exists"].add(("File", (("attached_to_doctype", CR), ("attached_to_name", "CR-1"),
                                      ("file_url", "/private/files/ky.pdf"))))
        hooks._check_signed_file(d, "/private/files/ky.pdf")

    def test_huy_tren_cong_khi_ban_tai_tay_dang_cho_kiem_giu_nguyen(self):
        # B-07
        _fresh("a@ec")
        hooks = importlib.import_module(P + "esign_hooks")
        d = _doc(signing_status=kol.SIGN_REVIEW, signed_file="/private/files/tay.pdf")
        r = hooks._contract(d, hooks.DESTROYED, None, "huy")
        self.assertFalse(r["changed"])
        self.assertEqual((d.signing_status, d.signed_file), (kol.SIGN_REVIEW, "/private/files/tay.pdf"))
        self.assertTrue(STATE["comments"])


class DnttTheoBrandHopDong(unittest.TestCase):
    """C5: DNTT tu hop dong KOL phai cung brand hop dong, SO cung brand."""

    def setUp(self):
        _fresh("a@ec")
        self.fund = importlib.import_module(P + "kol_funding")
        self.fund.kol_lookup.so_allowed = lambda u, so: (Row(name=so, ec_brand=self.so_brand), None)
        _doc(brand="Brand-A")

    def test_doi_brand_bi_chan(self):
        self.so_brand = "Brand-A"
        with self.assertRaises(Throw):
            self.fund.funding_validate(Doc(funding_source_name="CR-1", ec_brand="Brand-B", ec_sales_order="SO-1"), "a@ec")
        self.fund.funding_validate(Doc(funding_source_name="CR-1", ec_brand="Brand-A", ec_sales_order="SO-1"), "a@ec")

    def test_so_brand_khac_bi_chan(self):
        self.so_brand = "Brand-C"
        with self.assertRaises(Throw):
            self.fund.funding_validate(Doc(funding_source_name="CR-1", ec_brand="Brand-A", ec_sales_order="SO-1"), "a@ec")


class QuyTrinhKy(unittest.TestCase):
    def test_doi_kol_sang_mua_vao_bo_quy_trinh_rieng_kol(self):
        # A21
        from ecentric_workspace.approval_center.features.contract_review.domain import esign_flow as ef
        d = Doc(contract_type="Purchase / Mua vào (EC)", esign_flow=ef.KOL_PARTNER_SIGNED)
        self.assertIsNone(ef.apply_default(d))
        d = Doc(contract_type=kol.KOL_CONTRACT_TYPE, esign_flow=ef.KOL_PARTNER_SIGNED)
        self.assertEqual(ef.apply_default(d), ef.KOL_PARTNER_SIGNED)
        d = Doc(contract_type="Purchase / Mua vào (EC)", esign_flow=ef.PARTNER_SIGNED)
        self.assertEqual(ef.apply_default(d), ef.PARTNER_SIGNED)


class HopDongLaoDongKhongLenSharePoint(unittest.TestCase):
    def test_them_tep_o_buoc_duyet_bo_qua_hd_lao_dong(self):
        # B-09: "Them tep" (shared add_file -> dong_bo_mot_tep) truoc do dua ca HD lao dong len thu vien chung.
        _fresh("a@ec")
        wr = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
        sys.modules[wr.__name__] = wr
        sys.modules.pop("ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror", None)
        sp = importlib.import_module("ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror")
        STATE["values"][(CR, (("name", "CR-L"),))] = "Labor / Hợp đồng lao động (EC)"
        STATE["values"][(CR, (("name", "CR-K"),))] = kol.KOL_CONTRACT_TYPE
        self.assertFalse(sp.duoc_soi_guong_phieu(CR, "CR-L"))
        self.assertTrue(sp.duoc_soi_guong_phieu(CR, "CR-K"))
        self.assertIn("bo_qua", sp.dong_bo_mot_tep(CR, "CR-L", "/private/files/hd.pdf"))


def _service():
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.resubmit = lambda *a, **k: {}
    sys.modules[eng.__name__] = eng
    import ecentric_workspace.approval_center.shared.workflow as wf
    wf.transitions = eng
    sys.modules.pop(P + "service", None)
    return importlib.import_module(P + "service")


class HopDongDieuChinhKol(unittest.TestCase):
    def test_kol_san_co_khong_bao_gio_bo_cap_ceo(self):
        # R1: doi creator / tien tra nam ngoai DIFF_FIELDS -> "chi dieu chinh" lach CEO
        _fresh("a@ec")
        service = _service()
        base = dict(request_kind="Existing", previous_request="CR-0")
        self.assertFalse(service.skip_ceo(Doc(base, contract_type=kol.KOL_CONTRACT_TYPE), ["contract_value"]))
        self.assertTrue(service.skip_ceo(Doc(base, contract_type="Purchase / Mua vào (EC)"), ["contract_value"]))

    def test_hop_dong_goc_phong_khac_bi_chan(self):
        _fresh("x@ec")
        service = _service()
        STATE["values"][(CR, "CR-0")] = lambda f, d: Row(approval_request="AR-0", requested_by="khac@ec")
        STATE["values"][("EC Approval Request", "AR-0")] = "Approved"
        perms = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
        perms.can_view_request = lambda req, user=None, **k: user == k.get("requested_by")
        sys.modules[perms.__name__] = perms
        try:
            with self.assertRaises(Throw):
                service._require_approved_previous("CR-0")
            STATE["values"][(CR, "CR-0")] = lambda f, d: Row(approval_request="AR-0", requested_by="x@ec")
            service._require_approved_previous("CR-0")
        finally:
            sys.modules.pop(perms.__name__, None)


class SaoChepPhieu(unittest.TestCase):
    def test_khong_chep_hd_bbnt_sinh_tu_phieu_cu(self):
        # R2
        _fresh("a@ec")
        cs = importlib.import_module("ecentric_workspace.approval_center.shared.requests.command_service")
        self.assertTrue(cs._is_system_artefact("HDDV_05122026_HDDV.docx", CR))
        self.assertTrue(cs._is_system_artefact("BBNT_x_dot1.docx", CR))
        self.assertFalse(cs._is_system_artefact("HDDV_x.docx", "EC Payment Request"))
        self.assertTrue(cs._is_system_artefact("SIGNED-a.pdf"))


class DnttGuiLaiDoiNguon(unittest.TestCase):
    """R4: DNTT da gui theo HD KOL, luc bo sung doi sang PO chua duyet / bo nguon -> truoc lot chot."""

    def setUp(self):
        _fresh("acc@ec")
        self.ps = importlib.import_module("ecentric_workspace.approval_center.features.payment_request.application.service")
        self.calls = []
        self.ps.funding.validate_funding = lambda d: self.calls.append(d.funding_source_name)
        STATE["values"][("EC Payment Request", "PR-1")] = "EC Contract Review Request"   # nguon da luu

    def _pr(self, **kw):
        d = Doc(doctype="EC Payment Request", name="PR-1", approval_request="AR-9", requested_by="acc@ec",
                has_purchase_request="Yes", payment_amount=5)
        d.update(kw)
        return d

    def test_doi_sang_po_van_kiem_nguon(self):
        self.ps.normalize_payment(self._pr(funding_source_doctype="Purchase Order", funding_source_name="PO-1"))
        self.assertEqual(self.calls, ["PO-1"])

    def test_bo_nguon_bi_chan(self):
        with self.assertRaises(Throw):
            self.ps.normalize_payment(self._pr(has_purchase_request="No", funding_source_doctype="",
                                               funding_source_name=""))


class LichNghiLe(unittest.TestCase):
    def test_thieu_lich_nam_sau_thi_bao(self):
        # R5
        fk = _fresh("a@ec") and sys.modules["frappe"]
        lk = importlib.import_module(P + "kol_lookup")
        fk.defaults = types.SimpleNamespace(get_global_default=lambda k: "EC")
        fk.get_cached_value = lambda *a, **k: "HL-2026"
        STATE["values"][("Holiday List", "HL-2026")] = "2026-12-31"
        self.assertTrue(lk.holidays_cover(dt.date(2026, 12, 20)))
        self.assertFalse(lk.holidays_cover(dt.date(2027, 1, 4)))


class ChonMau(unittest.TestCase):
    def test_hai_mau_cung_diem_lay_ban_sua_gan_nhat(self):
        # A20
        _fresh("a@ec")
        lk = importlib.import_module(P + "kol_lookup")
        lk.list_templates = lambda kind=None: [
            {"name": "A-cu", "service_type": "Livestream", "modified": "2026-11-01 10:00:00"},
            {"name": "B-moi", "service_type": "Livestream", "modified": "2026-11-14 10:00:00"},
            {"name": "C-cu-hon", "service_type": "Livestream", "modified": "2026-10-01 10:00:00"}]
        lk.template_mismatch = lambda *a, **k: None
        self.assertEqual(lk.pick_template("Hợp đồng", "Cá nhân", "Livestream", False, "TikTok"), "B-moi")


class CheTruocKhiGuiAi(unittest.TestCase):
    """D4 / A15: email + PII da biet cua creator bi che."""

    def test_che_ngay_sinh_dia_chi_email_stk(self):
        _fresh("a@ec")
        ai = importlib.import_module(P + "kol_ai")
        text = ("sinh ngày 2/1/1999, cấp 10/05/2021 tại Cục CS QLHC. Địa chỉ: 12  Lê Lợi, Q1. Email b@gmail.com. "
                "TK 1.903.456.789. Giá 13.500.000, live 05/12/2026.")
        cr = {"ec_cr_dob": "1999-01-02", "ec_cr_cccd_issue_date": "2021-05-10", "ec_cr_address": "12 Lê Lợi, Q1",
              "ec_bank_account_no": "1903456789", "ec_cr_cccd_issue_place": "Cục CS QLHC"}
        out = ai.redact_known(text, cr)
        for leak in ("2/1/1999", "10/05/2021", "Cục CS", "Lê Lợi", "b@gmail.com", "1.903.456.789"):
            self.assertNotIn(leak, out)
        for keep in ("13.500.000", "05/12/2026"):
            self.assertIn(keep, out)


if __name__ == "__main__":
    unittest.main()
