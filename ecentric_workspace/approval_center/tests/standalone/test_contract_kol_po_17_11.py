# Copyright (c) 2026, eCentric and contributors
"""Quyet dinh PO 17/11/2026 cho hop dong KOL/KOC + form 27 (xem kol_access.py):

A. ban du thong tin creator chi nguoi tao creator + Ke toan tai (POST, ghi vet), nguoi khac khong thay URL;
B. KOL khong len thu vien SharePoint chung;  C. KOL khong lam "dieu chinh";
D. STK creator doi sau khi ky -> canh bao, Ke toan xac nhan thi luu;
+ 366 ngay, nha so HD cua phieu Tu choi / Huy, thanh ly hop dong, DNTT Booking KOL bat buoc chon HD,
  phieu thuong doi tep luc bo sung = duyet lai, Ke toan sua ten / loai creator, "Duyet thay boi".
"""
import ast
import datetime as dt
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                     # chay bang `python -m unittest <module>` (cong push) cung nap duoc
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Row, Throw, _fresh  # noqa: E402,F401
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
P = "ecentric_workspace.approval_center.features.contract_review.application."


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


def _access(user="req@ec", roles=None):
    _fresh(user)
    STATE["roles"].update(roles or {"fin@ec": ["EC Finance"]})
    pw = types.ModuleType("frappe.utils.password")
    pw.get_encryption_key = lambda: "site-key"
    sys.modules["frappe.utils.password"] = pw
    sys.modules["frappe"].utils.password = pw
    sys.modules.pop(P + "kol_access", None)
    return importlib.import_module(P + "kol_access")


def _kol(**kw):
    d = Doc(doctype=CR, name="CR-1", contract_type="KOL/KOC / Creator (EC)", creator="SUP-1",
            requested_by="req@ec", approval_request="AR-1", acceptances=[])
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    STATE["values"][("Supplier", "SUP-1")] = lambda field, as_dict: "owner@ec" if field == "owner" else None
    return d


def _biz():
    return {"name": "CR-1", "doctype": CR, "contract_type": "KOL/KOC / Creator (EC)", "creator": "SUP-1",
            "contract_file": "/private/files/HDDV_17112026_ab12cd34.docx",
            "request_attachment": None, "signed_file": "/private/files/hop dong ky.pdf",
            "acceptances": [{"bbnt_file": "/private/files/BBNT_1_x9y8z7w6.docx",
                             "signed_file": "/private/files/bbnt ky.pdf"}]}


# ----------------------------------------------------------------------------- A
class TaiBanDuPII(unittest.TestCase):
    def test_nhan_dien_tep_sinh_tu_mau(self):
        a = _access()
        for u in ("/private/files/HDDV_1_ab.docx", "BBNT_2.docx", "/f/SIGNED-HDDV_1.pdf", "REVIEW-BBNT_3.pdf"):
            self.assertTrue(a.is_generated(u), u)
        for u in ("/private/files/hop dong.docx", "", None, "/f/XHDDV_1.docx"):
            self.assertFalse(a.is_generated(u), u)

    def test_ai_duoc_tai(self):
        a = _access()
        b = _biz()
        STATE["values"][("Supplier", "SUP-1")] = "owner@ec"
        self.assertTrue(a.can_download_full(b, "fin@ec"))              # Ke toan
        self.assertTrue(a.can_download_full(b, "owner@ec"))            # nguoi tao creator
        self.assertTrue(a.can_download_full(b, "Administrator"))
        self.assertFalse(a.can_download_full(b, "req@ec"))             # nguoi khac (khong lap phieu nay)
        self.assertTrue(a.can_download_full(dict(b, requested_by="req@ec", approval_request="AR-1"), "req@ec"))
        # nhap (chua gui): nguoi lap chi xem ban che - khong "chon creator bat ky -> tai -> huy nhap"
        self.assertFalse(a.can_download_full(dict(b, requested_by="req@ec", approval_request=None), "req@ec"))
        self.assertFalse(a.can_download_full(dict(b, creator=None), "req@ec"))

    def test_nguoi_khong_duoc_tai_khong_thay_url(self):
        a = _access("req@ec")
        STATE["values"][("Supplier", "SUP-1")] = "owner@ec"
        b = _biz()
        a.redact_business(b)
        self.assertIsNone(b["contract_file"])
        self.assertIsNone(b["signed_file"])
        self.assertEqual((b["acceptances"][0]["bbnt_file"], b["acceptances"][0]["signed_file"]), (None, None))
        att = [{"file_name": "HDDV_17112026_ab12cd34.docx", "file_url": "/private/files/HDDV_17112026_ab12cd34.docx"},
               {"file_name": "hop dong ky.pdf", "file_url": "/private/files/hop dong ky.pdf"},
               {"file_name": "phu luc.pdf", "file_url": "/private/files/phu luc.pdf"}]
        self.assertEqual([x["file_name"] for x in a.redact_attachments(att, _biz())], ["phu luc.pdf"])

    def test_ke_toan_va_phieu_thuong_giu_nguyen(self):
        a = _access("fin@ec")
        b = _biz()
        a.redact_business(b)
        self.assertEqual(dict(b, has_contract_file=None, has_request_attachment=None, has_sign_pdf=None),
                         dict(_biz(), has_contract_file=None, has_request_attachment=None, has_sign_pdf=None))
        self.assertEqual((b["has_contract_file"], b["has_request_attachment"]), (True, False))
        a = _access("req@ec")
        b = dict(_biz(), contract_type="Sales / Bán ra (EC)")
        a.redact_business(b)
        self.assertEqual(b["contract_file"], _biz()["contract_file"])

    def _file(self, url="/private/files/HDDV_17112026_ab12cd34.docx"):
        key = ("File", tuple(sorted({"file_url": url, "attached_to_doctype": CR, "attached_to_name": "CR-1"}.items())))
        STATE["values"][key] = Row(name="F-1", file_name=url.rsplit("/", 1)[-1])
        STATE["docs"][("File", "F-1")] = types.SimpleNamespace(get_content=lambda: b"DOCX")

    def test_tai_ghi_vet_va_chan_dung_nguoi(self):
        a = _access("fin@ec")
        _kol()
        self._file()
        name, content = a.download_file("CR-1", "/private/files/HDDV_17112026_ab12cd34.docx", "fin@ec")
        self.assertEqual((name, content), ("HDDV_17112026_ab12cd34.docx", b"DOCX"))
        # vet ghi NHAN tep, khong ghi ten tep (doan ngau nhien la mot phan URL)
        self.assertTrue(any("fin@ec" in c and "hợp đồng" in c for c in STATE["comments"]))
        self.assertFalse(any("ab12cd34" in c for c in STATE["comments"]))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.download_file("CR-1", "/private/files/HDDV_17112026_ab12cd34.docx", "duyet@ec")
        # PO 17/11 (sau QC): nguoi lap chinh phieu nay tai duoc (gui creator ky, xuat PDF len cong)
        self.assertEqual(a.download_file("CR-1", "/private/files/HDDV_17112026_ab12cd34.docx", "req@ec")[1], b"DOCX")

    def test_khong_tai_tep_la_hay_tep_phieu_khac(self):
        a = _access("fin@ec")
        _kol()
        with self.assertRaises(Throw):                      # tep nguoi dung, khong phai ban ky / ban mau
            a.download_file("CR-1", "/private/files/phu luc.pdf", "fin@ec")
        key = ("File", tuple(sorted({"file_url": "/private/files/HDDV_khac.docx", "attached_to_doctype": CR,
                                     "attached_to_name": "CR-1"}.items())))
        STATE["values"][key] = lambda field, as_dict: None
        with self.assertRaises(Throw):                      # ten HDDV_ nhung khong gan phieu nay
            a.download_file("CR-1", "/private/files/HDDV_khac.docx", "fin@ec")
        _kol(contract_type="Sales / Bán ra (EC)")
        self._file()
        with self.assertRaises(Throw):
            a.download_file("CR-1", "/private/files/HDDV_17112026_ab12cd34.docx", "fin@ec")

    def test_ban_ky_cung_tai_qua_cong_nay(self):
        a = _access("fin@ec")
        _kol(signed_file="/private/files/hop dong ky.pdf")
        self._file("/private/files/hop dong ky.pdf")
        self.assertEqual(a.download_file("CR-1", "/private/files/hop dong ky.pdf", "fin@ec")[1], b"DOCX")

    def test_endpoint_post_va_tep_he_thong_chu_admin_ten_ngau_nhien(self):
        api = _read("features/contract_review/controllers/kol_api.py")
        i = api.index("def kol_download_file")
        self.assertIn('@frappe.whitelist(methods=["POST"])', api[api.rindex("\n@", 0, i) - 1:i])
        self.assertIn('frappe.local.response.type = "download"', api[i:i + 600])
        files = _read("features/contract_review/application/kol_files.py")
        self.assertIn("generate_hash(length=8)", files)
        self.assertIn('"owner", "Administrator"', files)
        q = _read("shared/requests/query_service.py")
        self.assertIn("attachment_redactor", q)
        self.assertIn("attachments, doi_chung = [], []", q)  # loi redactor -> khong tra tep nao (fail-closed)
        self.assertIn("doi_chung = definition.attachment_redactor(doi_chung", q)

    def test_nguoi_duyet_xem_ban_che_chi_doc(self):
        src = _read("features/contract_review/application/kol_preview.py")
        self.assertIn("is_approver(doc, user) or kol_lookup.is_finance(user)", src)
        self.assertIn("return doc, set()", src)


# ----------------------------------------------------------------------------- B
class KhongLenSharePoint(unittest.TestCase):
    def test_bo_qua_ca_lao_dong_va_kol(self):
        src = _read("shared/integrations/sharepoint_mirror.py")
        tree = ast.parse(src)
        val = [n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "BO_QUA_PHIEU"][0]
        rule = ast.literal_eval(val.value)["EC Contract Review Request"]
        self.assertEqual(rule[0], "contract_type")
        self.assertIn("KOL/KOC / Creator (EC)", rule[1])
        self.assertIn("Labor / Hợp đồng lao động (EC)", rule[1])
        # dong_bo_phieu (probe / patch goi thang) cung chot theo phieu
        i = src.index("\ndef dong_bo_phieu(")
        self.assertIn("duoc_soi_guong_phieu(business_doctype, business_name)", src[i:i + 3000])

    def test_service_khong_xep_viec_cho_kol_va_loi_thi_khong_len(self):
        svc = _read("features/contract_review/application/service.py")
        self.assertIn("_KHONG_LEN_SHAREPOINT = (esign_flow.LABOR_CONTRACT_TYPE, esign_flow.KOL_CONTRACT_TYPE)", svc)
        i = svc.index("def _is_labor")
        self.assertIn("return True", svc[i:i + 900])


# ----------------------------------------------------------------------------- C
class KolKhongDieuChinh(unittest.TestCase):
    def test_chan_existing(self):
        s, _v, _a, _f = _fresh("req@ec")
        s.creator_row = lambda n: {"ec_cr_type": "Cá nhân", "supplier_name": "A"}
        s.kol.validate_kol = lambda d, t, today=None: []
        d = Doc(doctype=CR, name="CR-9", contract_type="KOL/KOC / Creator (EC)", creator="SUP-1",
                request_kind="Existing", request_type=s.kol.TEMPLATE_EC)
        with self.assertRaises(Throw) as cm:
            s.validate_submit(d)
        self.assertIn("Hợp đồng / phụ lục MỚI", str(cm.exception))

    def test_trang_khoa_va_tu_doi_ve_moi(self):
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('if(d.request_kind==="Existing" && KOL.isKol(d)) errs.request_kind=', html)
        i = html.index('if(k==="contract_type"&&KOL.isKol(state.draft)&&state.draft.request_kind==="Existing")')
        self.assertLess(i, html.index('if(prevData() && DIFF_FIELDS.indexOf(k)>=0)'))   # truoc nhanh tra ve som
        self.assertIn('r.get("contract_type") != "KOL/KOC / Creator (EC)"',
                      _read("features/contract_review/controllers/api.py"))


# ----------------------------------------------------------------------------- D
class TaiKhoanNhanTien(unittest.TestCase):
    def test_van_tay_chuan_hoa_va_khong_luu_so(self):
        a = _access()
        f1 = a.payee_fp({"ec_bank_account_no": "0011 2233-44", "ec_bank_name": "Vietcombank"})
        f2 = a.payee_fp({"ec_bank_account_no": "0011223344", "ec_bank_name": " VIETCOMBANK "})
        self.assertEqual(f1, f2)
        self.assertNotEqual(f1, a.payee_fp({"ec_bank_account_no": "0011223345", "ec_bank_name": "Vietcombank"}))
        self.assertNotEqual(f1, a.payee_fp({"ec_bank_account_no": "0011223344", "ec_bank_name": "Techcombank"}))
        self.assertEqual(a.payee_fp({"ec_bank_account_no": "", "ec_bank_name": "X"}), "")
        self.assertNotIn("0011223344", f1)
        self.assertEqual(len(f1), 32)

    def test_doi_stk_canh_bao_ke_toan_xac_nhan_thi_het(self):
        a = _access("fin@ec")
        old = {"ec_bank_account_no": "111", "ec_bank_name": "VCB"}
        new = {"ec_bank_account_no": "222", "ec_bank_name": "VCB"}
        d = _kol()
        STATE["values"][("EC Approval Request", "AR-1")] = "Pending"
        a.snapshot_payee(d, old)
        self.assertFalse(a.payee_changed(d, old))
        self.assertTrue(a.payee_changed(d, new))
        ks = importlib.import_module(P + "kol_service")
        ks.creator_row = lambda n: new
        sets = []
        sys.modules["frappe"].db.set_value = lambda dt_, n, f, v=None, **k: sets.append((f, v))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.confirm_payee("CR-1", "req@ec")
        with self.assertRaises(Throw):                      # chua duyet xong: phai bo sung + tao lai HD
            a.confirm_payee("CR-1", "fin@ec")
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        self.assertEqual(a.confirm_payee("CR-1", "fin@ec"), {"ok": True, "changed": True})
        (field, val), = sets
        self.assertEqual(field, "kol_payee_ok")
        d["kol_payee_ok"] = val
        self.assertFalse(a.payee_changed(d, new))           # da luu -> khong bao lai
        self.assertTrue(a.payee_changed(d, {"ec_bank_account_no": "333", "ec_bank_name": "VCB"}))
        self.assertEqual(a.confirm_payee("CR-1", "fin@ec")["changed"], False)   # bam lai: khong nhan doi

    def test_phieu_cu_chua_chot_khong_bao(self):
        a = _access()
        self.assertFalse(a.payee_changed(_kol(), {"ec_bank_account_no": "9", "ec_bank_name": "X"}))

    def test_chot_luc_gui_va_canh_bao_luc_bbnt(self):
        svc = _read("features/contract_review/application/kol_service.py")
        self.assertLess(svc.index("fill_partner_signer(doc, creator)", svc.index("def validate_submit")),
                        svc.index("kol_access.snapshot_payee(doc, creator)"))
        acc = _read("features/contract_review/application/kol_acceptance.py")
        self.assertIn("_payee_note(doc, row.idx)", acc)


# ----------------------------------------------------------------------------- thanh ly
class ThanhLy(unittest.TestCase):
    def test_chi_ke_toan_co_ly_do_hd_da_duyet(self):
        a = _access("fin@ec")
        sets = []
        sys.modules["frappe"].db.set_value = lambda dt_, n, f, v=None, **k: sets.append(f)
        d = _kol()
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.close_contract("CR-1", "req@ec", "x")
        with self.assertRaises(Throw):
            a.close_contract("CR-1", "fin@ec", "  ")
        STATE["values"][("EC Approval Request", "AR-1")] = "Pending"
        with self.assertRaises(Throw):
            a.close_contract("CR-1", "fin@ec", "creator huy")
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        a.close_contract("CR-1", "fin@ec", "creator huy")
        self.assertEqual(sets[0]["kol_closed_by"], "fin@ec")
        a.require_open(d)
        d["kol_closed_at"] = "2026-11-17 10:00:00"
        with self.assertRaises(Throw):
            a.require_open(d)

    def test_tao_va_gui_bbnt_deu_chan(self):
        acc = _read("features/contract_review/application/kol_acceptance.py")
        for fn in ("def add_acceptance", "def send_acceptance"):
            i = acc.index(fn)
            self.assertIn("kol_access.require_open(doc)", acc[i:i + 1500], fn)


# ----------------------------------------------------------------------------- so HD + 366 ngay
class SoHopDong(unittest.TestCase):
    def test_phieu_tu_choi_huy_nha_so(self):
        s, _v, _a, _f = _fresh("req@ec")
        STATE["get_all"][CR] = [Row(contract_no="B-1", approval_request="AR-R"),
                                Row(contract_no="B-2", approval_request="AR-P"),
                                Row(contract_no="B-3", approval_request=None)]
        STATE["get_all"]["EC Approval Request"] = lambda f, kw: ["AR-R"]
        self.assertEqual(s._numbers_in_use("B", "CR-X"), {"B-2", "B-3"})

    def test_toi_366_ngay(self):
        T = importlib.import_module("ecentric_workspace.approval_center.features.contract_review.domain.kol_texts")
        today = dt.date(2026, 11, 15)
        self.assertEqual(len(T.parse_service_dates("05/12/2026, 01/12/2027", today)), 2)
        with self.assertRaises(ValueError):
            T.parse_service_dates("05/12/2026, 28/12/2027", today)


# ----------------------------------------------------------------------------- creator
class KeToanSuaCreator(unittest.TestCase):
    def _svc(self):
        from test_creators_service import EXISTING, FakeRepo
        from ecentric_workspace.approval_center.shared.creators.service import CreatorService
        repo = FakeRepo([EXISTING], {"ke.toan@ec": ["EC Finance"]})
        return CreatorService(repo), repo

    def test_ke_toan_doi_ten_loai_co_ghi_chu(self):
        svc, repo = self._svc()
        svc.update("ke.toan@ec", "SUP-001", {"supplier_name": "Nguyễn Thị Hảo B", "ec_cr_type": "Hộ kinh doanh",
                                             "tax_id": "0312345678"})
        row = repo.rows["SUP-001"]
        self.assertEqual((row["supplier_name"], row["ec_cr_type"]), ("Nguyễn Thị Hảo B", "Hộ kinh doanh"))
        self.assertTrue(row.get("supplier_type"))
        note = " ".join(repo.notes)
        self.assertIn('ke.toan@ec đổi tên creator: "Nguyễn Thị Hảo" -> "Nguyễn Thị Hảo B".', note)
        self.assertIn('đổi loại creator: "Cá nhân" -> "Hộ kinh doanh".', note)

    def test_chu_ban_ghi_khong_doi_duoc_ten(self):
        svc, repo = self._svc()
        svc.update("an@ec", "SUP-001", {"supplier_name": "Tên khác"})
        self.assertEqual(repo.rows["SUP-001"]["supplier_name"], "Nguyễn Thị Hảo")

    def test_khac_loai_trung_cung_chi_hoi(self):
        from ecentric_workspace.approval_center.shared.creators import domain
        rows = [{"name": "SUP-1", "supplier_name": "A", "ec_cr_type": "Cá nhân", "ec_cr_cccd": "001099000111"}]
        hit = domain.classify_duplicates({"ec_cr_type": "Hộ kinh doanh", "ec_cr_cccd": "001099000111"}, rows)
        self.assertFalse(hit["hard"])
        self.assertTrue(hit["soft"])
        hit = domain.classify_duplicates({"ec_cr_type": "Cá nhân", "ec_cr_cccd": "001099000111"}, rows)
        self.assertTrue(hit["hard"])


# ----------------------------------------------------------------------------- form 27 thuong + DNTT
class PhieuThuongVaDntt(unittest.TestCase):
    def test_chu_ky_duyet_tinh_tep_nguoi_gui_chi_phieu_thuong(self):
        svc = _read("features/contract_review/application/service.py")
        i = svc.index("def _signature")
        body = svc[i:svc.index("\ndef ", i + 10)]
        self.assertIn("if not kol.is_kol(doc):", body)
        self.assertIn('vals["__files"]', body)
        self.assertIn('"owner": doc.requested_by', svc)
        self.assertIn("p397_chu_ky_duyet_hop_dong_tep", _read("../patches.txt"))

    def test_p397_chi_tinh_lai_phieu_cho_duyet_chua_ai_sua(self):
        _fresh()
        fk = sys.modules["frappe"]
        p397 = importlib.import_module("ecentric_workspace.approval_center.patches.p397_chu_ky_duyet_hop_dong_tep")
        importlib.reload(p397)
        svc = types.SimpleNamespace(MATERIAL_FIELDS=["contract_value"], _signature=lambda r: "NEW-" + r.name)
        fk.get_module = lambda path: svc
        STATE["exists"].add(("DocType", CR))
        old = p397._old_sig({"contract_value": 5}, ["contract_value"])
        STATE["get_all"][CR] = [Row(name="A", approval_request="R-A", material_signature=old, contract_value=5),
                                Row(name="B", approval_request="R-B", material_signature="khac", contract_value=5),
                                Row(name="C", approval_request="R-C", material_signature=old, contract_value=5)]
        STATE["values"].update({("EC Approval Request", "R-A"): "Pending", ("EC Approval Request", "R-B"): "Pending",
                                ("EC Approval Request", "R-C"): "Information Required"})
        sets = []
        fk.db.set_value = lambda dt_, n, f, v=None, **k: sets.append((n, f, v, k.get("update_modified")))
        fk.logger = lambda *a: types.SimpleNamespace(info=lambda *x: None)
        p397.execute()
        self.assertEqual(sets, [("A", "material_signature", "NEW-A", False)])

    def test_dntt_booking_kol_bat_buoc_hop_dong(self):
        sys.modules.pop("ecentric_workspace.approval_center.features.payment_request.application.funding", None)
        _fresh()
        fu = importlib.import_module("ecentric_workspace.approval_center.features.payment_request.application.funding")
        self.assertEqual(fu.required_source("TT_KOL")[0], "EC Contract Review Request")
        self.assertIsNone(fu.required_source("TT_KHAC"))
        self.assertIsNone(fu.required_source(None))
        svc = _read("features/payment_request/application/service.py")
        self.assertIn('need = funding.required_source(', svc)
        i = svc.index("def normalize_payment")
        self.assertIn("_require_source(doc)", svc[i:svc.index("\ndef ", i + 10)])   # ca luc gui lai sau bo sung

    def test_duyet_thay_boi_co_level_no(self):
        q = _read("shared/requests/query_service.py")
        i = q.index('"level_no"')
        self.assertLess(q.rfind("EC Approval Action", 0, i), i)

    def test_tao_phieu_moi_tu_phieu_nay(self):
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('data-act="clone"', html)
        self.assertIn('if(a==="clone") return doClone(name);', html)
        self.assertIn('call("clone_request",{name:name})', html)

    def test_trang_tai_qua_post_khong_lo_url(self):
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('kol_download_file",{method:"POST"', html)
        self.assertIn('"X-Frappe-CSRF-Token"', html)
        self.assertIn('"kol_download_file"', html)
        self.assertNotIn('href="\'+esc(b.contract_file)', html)
        self.assertNotIn('href="\'+esc(r.bbnt_file)', html)
        self.assertNotIn('href="\'+esc(b.signed_file)', html)


# ----------------------------------------------------------------------------- QC 17/11 (sua sau vong agent)
class QcSauVongAgent(unittest.TestCase):
    def test_ban_review_va_doi_chung_cung_la_ban_du(self):
        a = _access()
        for u in ("REVIEW-1a2b3c4d-HDDV_17112026_ab12cd34.docx", "[Đối chứng] HDDV_1.docx – Duyệt – x.docx",
                  "SIGNED-REVIEW-1a2b3c4d-BBNT_1.pdf"):
            self.assertTrue(a.is_generated(u), u)
        self.assertFalse(a.is_generated("REVIEW-1a2b3c4d-phu luc.pdf"))

    def test_nguoi_duoc_tai_cung_khong_mo_thang_tu_dinh_kem(self):
        a = _access("fin@ec")
        att = [{"file_name": "HDDV_1_ab.docx", "file_url": "/private/files/HDDV_1_ab.docx"},
               {"file_name": "phu luc.pdf", "file_url": "/private/files/phu luc.pdf"}]
        self.assertEqual([x["file_name"] for x in a.redact_attachments(att, _biz())], ["phu luc.pdf"])
        dc = [{"name": "S1", "docx_file_url": "/private/files/x.docx", "pdf_file_url": "/private/files/x.pdf"}]
        self.assertEqual(a.redact_attachments(dc, _biz()), dc)          # Ke toan van thay ban doi chung
        a = _access("req@ec")
        STATE["values"][("Supplier", "SUP-1")] = "owner@ec"
        self.assertEqual(a.redact_attachments(dc, _biz()), [])          # nguoi khong duoc tai: an

    def test_endpoint_khong_tra_url_cho_nguoi_khong_duoc_tai(self):
        a = _access("req@ec")
        STATE["values"][("Supplier", "SUP-1")] = "owner@ec"
        self.assertEqual(a.strip_url(_biz(), {"contract_file": "/f/HDDV_1.docx", "x": 1}, "contract_file"),
                         {"contract_file": None, "x": 1})
        a = _access("fin@ec")
        self.assertEqual(a.strip_url(_biz(), {"bbnt_file": "/f/B.docx"}, "bbnt_file"), {"bbnt_file": "/f/B.docx"})
        api = _read("features/contract_review/controllers/kol_api.py")
        for fn, f in (("kol_generate_contract", '"contract_file"'), ("kol_add_acceptance", '"bbnt_file"'),
                      ("kol_send_acceptance", '"bbnt_file"')):
            i = api.index("def " + fn)
            self.assertIn("_no_pii_url(name", api[i:i + 400], fn)
            self.assertIn(f, api[i:i + 400], fn)

    def test_thanh_ly_chan_tai_ban_ky_moi(self):
        s, _v, _a, _f = _fresh("req@ec")
        _kol(kol_closed_at="2026-11-17 10:00:00", signing_status="Chưa ký")
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        with self.assertRaises(Throw) as cm:
            s.mark_signed("CR-1", "/private/files/ky.pdf", "req@ec")
        self.assertIn("thanh lý", str(cm.exception))

    def test_trung_khac_loai_chi_mem_giua_ca_nhan_va_ho_kinh_doanh(self):
        from ecentric_workspace.approval_center.shared.creators import domain
        rows = [{"name": "SUP-1", "supplier_name": "A", "ec_cr_type": "Cá nhân", "ec_bank_account_no": "0011223344"}]
        hit = domain.classify_duplicates({"ec_cr_type": "Công ty", "ec_bank_account_no": "0011223344"}, rows)
        self.assertTrue(hit["hard"])                                     # cong ty dung STK ca nhan: chan
        hit = domain.classify_duplicates({"ec_cr_type": "Hộ kinh doanh", "ec_bank_account_no": "0011223344"}, rows)
        self.assertFalse(hit["hard"])

    def test_khong_doi_loai_khi_da_co_hop_dong_duyet(self):
        sys.path.insert(0, HERE)
        from test_creators_service import EXISTING, FakeRepo
        from ecentric_workspace.approval_center.shared.creators.service import CreatorError, CreatorService
        repo = FakeRepo([EXISTING], {"ke.toan@ec": ["EC Finance"]})
        repo.approved_contract = lambda n: "EC-CTR-1"
        with self.assertRaises(CreatorError):
            CreatorService(repo).update("ke.toan@ec", "SUP-001", {"ec_cr_type": "Hộ kinh doanh", "tax_id": "0312345678"})
        CreatorService(repo).update("ke.toan@ec", "SUP-001", {"supplier_name": "Nguyễn Thị Hảo C"})   # doi ten van duoc
        self.assertEqual(repo.rows["SUP-001"]["supplier_name"], "Nguyễn Thị Hảo C")

    def test_chu_ky_bo_tep_he_thong(self):
        svc = _read("features/contract_review/application/service.py")
        self.assertIn('_SYSTEM_FILE_PREFIXES = ("SIGNED-", "REVIEW-", "[Đối chứng]")', svc)

    def test_dntt_tai_khoan_phai_khop_creator(self):
        src = _read("features/contract_review/application/kol_funding.py")
        i = src.index("def funding_validate")
        self.assertIn("_check_payee(pr)", src[i:])
        j = src.index("def _check_payee")
        body = src[j:]
        self.assertIn("kol_access.payee_changed(doc, creator)", body)
        self.assertIn('pr.get("bank_account_number")', body)

    def test_dntt_hop_dong_tool_cu_ghi_so_cu(self):
        _fresh("req@ec")
        fu = importlib.import_module(P + "kol_funding")
        erp = []
        STATE["get_all"][CR] = lambda f, kw: list(erp)
        pr = lambda reason: {"has_purchase_request": "No", "no_purchase_request_reason": reason}
        self.assertTrue(fu.legacy_contract_ref(pr("HĐ cũ (số 05112026/HDDV/ECENTRIC-NTP.FCV).")))
        erp.append(Row(name="EC-CTR-9", contract_no="05112026/HDDV/ECENTRIC-NTP.FCV", approval_request="AR-9"))
        STATE["values"][("EC Approval Request", "AR-9")] = "Rejected"
        self.assertTrue(fu.legacy_contract_ref(pr("05112026/HDDV/ECENTRIC-NTP.FCV")))   # HD ERP bi tu choi: khong chan
        STATE["values"][("EC Approval Request", "AR-9")] = "Approved"
        for reason in ("05112026/HDDV/ECENTRIC-NTP.FCV", "HD 05112026/HDDV/ECENTRIC-NTP.FCV-đợt 2",
                       "05112026/HDDV/ECENTRIC-NTP.FCV_dot2", "cũ 01012025/HDDV/ECENTRIC-A.B thay 05112026/HDDV/ECENTRIC-NTP.FCV"):
            with self.assertRaises(Throw, msg=reason):
                fu.legacy_contract_ref(pr(reason))
        self.assertFalse(fu.legacy_contract_ref(pr("khong co so")))
        self.assertFalse(fu.legacy_contract_ref({"has_purchase_request": "Yes",
                                                 "no_purchase_request_reason": "05112026/HDDV/ECENTRIC-A.B"}))
        svc = _read("features/payment_request/application/service.py")
        self.assertIn("funding.legacy_allowed(need[0], doc)", svc)

    def test_dntt_hop_dong_tool_cu_dang_hddv_truoc_ngay(self):
        """18/11 (Linh, EC-PAYR-2026-00693): so HD cu dang "HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC" (HDDV truoc
        ngay, khong co ".mau") truoc bi bao "phai gan hop dong KOL" du da chon No + ghi so."""
        _fresh("req@ec")
        fu = importlib.import_module(P + "kol_funding")
        erp = []
        STATE["get_all"][CR] = lambda f, kw: list(erp)
        pr = lambda reason: {"has_purchase_request": "No", "no_purchase_request_reason": reason}
        for reason in ("Thanh toán đợt 2 cho hợp đồng số HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC",
                       "HĐDV/01102026/ABC-ECENTRIC-X", "09102026/HDDV/ECENTRIC-XOAIFAM.DL",
                       "12112026/HDDV/ECENTRIC-TC-HT(L.PHN"):
            self.assertTrue(fu.legacy_contract_ref(pr(reason)), reason)
        for reason in ("Booking KOL/KOC", "Booking KOL KOC", "HDDV", "HDDV/2026/ABC", "x/HDDV/09102026/ABC"):
            self.assertFalse(fu.legacy_contract_ref(pr(reason)), reason)
        # so HD dang moi trung hop dong ERP con hieu luc -> van chan nhu dang cu
        erp.append(Row(name="EC-CTR-8", contract_no="HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC", approval_request="AR-8"))
        STATE["values"][("EC Approval Request", "AR-8")] = "Approved"
        with self.assertRaises(Throw):
            fu.legacy_contract_ref(pr("so HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC"))
        # cau bao khi da chon No ma chua nhan ra so: chi dung o va 2 vi du dinh dang
        svc = _read("features/payment_request/application/service.py")
        self.assertIn('if doc.get("has_purchase_request") == "No":', svc)
        self.assertIn("HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC", svc)

    def test_dinh_kem_pii_theo_chu_tep(self):
        a = _access("duyet@ec")
        STATE["values"][("Supplier", "SUP-1")] = "owner@ec"
        b = _biz()
        att = [{"file_name": "HDDV_05112026.pdf", "file_url": "/private/files/HDDV_05112026.pdf", "owner": "req@ec"},
               {"file_name": "HDDV_cu.docx", "file_url": "/private/files/HDDV_cu.docx", "owner": "req@ec"},
               {"file_name": "ky bi tra.pdf", "file_url": "/private/files/ky bi tra.pdf", "owner": "Administrator"},
               {"file_name": "phu luc.pdf", "file_url": "/private/files/phu luc.pdf", "owner": "req@ec"}]
        # nguoi duyet: an ca PDF nguoi lap xuat tu Word (HDDV_...pdf) - QC ban do 17/11
        self.assertEqual([x["file_name"] for x in a.redact_attachments(att, b)], ["phu luc.pdf"])
        a = _access("fin@ec")
        self.assertEqual([x["file_name"] for x in a.redact_attachments(att, b)], ["HDDV_05112026.pdf", "phu luc.pdf"])

    def test_nhan_ban_ky_chuyen_chu_tep(self):
        src = _read("features/contract_review/application/kol_files.py")
        i = src.index("def claim_upload")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('"owner": "Administrator"', body)
        self.assertIn('frappe.db.set_value("File", r.name, "owner", "Administrator"', body)

    def test_creator_ngung_dung_thi_trung_chi_hoi(self):
        from ecentric_workspace.approval_center.shared.creators import domain
        rows = [{"name": "SUP-1", "supplier_name": "A", "ec_cr_type": "Công ty", "tax_id": "0312345678", "disabled": 1}]
        hit = domain.classify_duplicates({"ec_cr_type": "Công ty", "tax_id": "0312345678"}, rows)
        self.assertFalse(hit["hard"])
        self.assertTrue(hit["soft"])
        from test_creators_service import EXISTING, FakeRepo
        from ecentric_workspace.approval_center.shared.creators.service import CreatorService
        repo = FakeRepo([EXISTING], {"ke.toan@ec": ["EC Finance"]})
        CreatorService(repo).update("ke.toan@ec", "SUP-001", {"disabled": 1})
        self.assertEqual(repo.rows["SUP-001"]["disabled"], 1)
        self.assertIn("ngừng dùng", " ".join(repo.notes))
        CreatorService(repo).update("an@ec", "SUP-001", {"disabled": 0})     # chu ban ghi khong bat lai duoc
        self.assertEqual(repo.rows["SUP-001"]["disabled"], 1)

    def test_p399_chot_moc_cho_hop_dong_cu(self):
        _fresh()
        fk = sys.modules["frappe"]
        p = importlib.import_module("ecentric_workspace.approval_center.patches.p399_kol_van_tay_tai_khoan")
        importlib.reload(p)
        STATE["exists"].add(("DocType", CR))
        fk.db.has_column = lambda dt_, c: True
        acc = types.SimpleNamespace(payee_fp=lambda c: "FP-" + c["ec_bank_account_no"] if c.get("ec_bank_account_no") else "")
        svc = types.SimpleNamespace(creator_row=lambda n: {"ec_bank_account_no": "1"} if n != "SUP-X" else {})
        fk.get_module = lambda path: acc if path.endswith("kol_access") else svc
        STATE["get_all"][CR] = [Row(name="A", creator="SUP-1", approval_request="R-A", kol_payee_fp=None),
                                Row(name="B", creator="SUP-1", approval_request="R-B", kol_payee_fp="old"),
                                Row(name="C", creator="SUP-1", approval_request="R-C", kol_payee_fp=None),
                                Row(name="D", creator="SUP-X", approval_request="R-D", kol_payee_fp=None)]
        STATE["values"].update({("EC Approval Request", "R-A"): "Approved", ("EC Approval Request", "R-C"): "Rejected",
                                ("EC Approval Request", "R-D"): "Pending"})
        sets = []
        fk.db.set_value = lambda dt_, n, f, v=None, **k: sets.append((n, v))
        fk.logger = lambda *a: types.SimpleNamespace(info=lambda *x: None)
        p.execute()
        # creator chua co STK -> moc "-" (STK them sau cung phai Ke toan xac nhan)
        self.assertEqual(sets, [("A", "FP-1"), ("D", "-")])


# ----------------------------------------------------------------------------- QC ban do + UI 17/11
class QcBanDo(unittest.TestCase):
    def test_xoa_stk_cung_la_doi(self):
        a = _access()
        d = _kol()
        a.snapshot_payee(d, {"ec_bank_account_no": "111", "ec_bank_name": "VCB"})
        self.assertTrue(a.payee_changed(d, {"ec_bank_account_no": "", "ec_bank_name": "VCB"}))

    def test_dntt_creator_khong_co_stk_bi_chan_va_dien_san_stk(self):
        src = _read("features/contract_review/application/kol_funding.py")
        j = src.index("def _check_payee")
        self.assertIn("if not stored:", src[j:])
        i = src.index("def fill_payment")
        self.assertIn("pr.bank_account_number = creator.get(\"ec_bank_account_no\")", src[i:j])

    def test_ngoai_le_tool_cu_chan_ca_hd_dang_duyet_va_so_brand_co_gach(self):
        _fresh("req@ec")
        fu = importlib.import_module(P + "kol_funding")
        erp = [Row(name="EC-CTR-7", contract_no="05112026/HDDV/ECENTRIC-NTP.FRL-VN", approval_request="AR-7"),
               Row(name="EC-CTR-8", contract_no="05112026/HDDV/ECENTRIC-NTP.FCV-1", approval_request="AR-8")]
        STATE["get_all"][CR] = lambda f, kw: list(erp)
        STATE["values"].update({("EC Approval Request", "AR-7"): "Pending", ("EC Approval Request", "AR-8"): "Approved"})
        pr = lambda r: {"has_purchase_request": "No", "no_purchase_request_reason": r}
        with self.assertRaises(Throw) as cm:
            fu.legacy_contract_ref(pr("HĐ 05112026/HDDV/ECENTRIC-NTP.FRL-VN"))
        self.assertIn("đang duyệt", str(cm.exception))
        self.assertTrue(fu.legacy_contract_ref(pr("05112026/HDDV/ECENTRIC-NTP.FCV-12")))   # khong khop "-1"
        with self.assertRaises(Throw):
            fu.legacy_contract_ref(pr("05112026/HDDV/ECENTRIC-NTP.FCV-1-dot2"))

    def test_ky_sau_thanh_ly_khong_mo_coc(self):
        _s, _v, acc, _f = _fresh("fin@ec")
        d = _kol(signing_status="Đã ký đủ", advance_amount=3_000_000, payable_amount=10_000_000,
                 signed_at="2026-11-18 09:00:00", kol_closed_at="2026-11-17 10:00:00")
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        self.assertEqual(acc.payable_cap(d), 0.0)
        d["signed_at"] = "2026-11-16 09:00:00"                 # ky truoc khi thanh ly: coc van tinh
        self.assertEqual(acc.payable_cap(d), 3_000_000)

    def test_tai_phai_xem_duoc_phieu_va_mo_lai_thanh_ly(self):
        src = _read("features/contract_review/application/kol_access.py")
        self.assertIn("not can_download_full(doc, user) or not _can_view(doc, user)", src)
        a = _access("fin@ec")
        sets = []
        sys.modules["frappe"].db.set_value = lambda dt_, n, f, v=None, **k: sets.append(f)
        _kol(kol_closed_at="2026-11-17 10:00:00", kol_close_reason="x")
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.reopen_contract("CR-1", "req@ec", "nham")
        with self.assertRaises(Throw):
            a.reopen_contract("CR-1", "fin@ec", " ")
        a.reopen_contract("CR-1", "fin@ec", "thanh ly nham")
        self.assertEqual(sets[0]["kol_closed_at"], None)
        self.assertTrue(any("mở lại" in c for c in STATE["comments"]))

    def test_creator_ngung_dung_sua_duoc_du_da_co_ban_thay(self):
        from ecentric_workspace.approval_center.shared.creators import domain
        rows = [{"name": "SUP-2", "supplier_name": "Y", "ec_cr_type": "Cá nhân", "ec_bank_account_no": "0011223344"}]
        hit = domain.classify_duplicates({"ec_cr_type": "Công ty", "ec_bank_account_no": "0011223344", "disabled": 1}, rows)
        self.assertFalse(hit["hard"])

    def test_truong_tep_o_permlevel_1(self):
        import json as _j
        d = _j.loads(_read("doctype/ec_contract_review_request/ec_contract_review_request.json"))
        lv = {f["fieldname"]: f.get("permlevel", 0) for f in d["fields"]}
        self.assertEqual((lv["contract_file"], lv["signed_file"], lv["request_attachment"]), (1, 1, 1))
        self.assertTrue(any(p.get("permlevel") == 1 and p.get("role") == "System Manager" for p in d["permissions"]))
        c = _j.loads(_read("doctype/ec_contract_acceptance/ec_contract_acceptance.json"))
        lv = {f["fieldname"]: f.get("permlevel", 0) for f in c["fields"]}
        self.assertEqual((lv["bbnt_file"], lv["signed_file"]), (1, 1))


# ----------------------------------------------------------------------------- QC he thong vong 3 17/11
class QcHeThong(unittest.TestCase):
    def test_luu_phieu_tra_chu_tep_pii_ve_admin(self):
        a = _access("req@ec")
        d = _kol(contract_file="/private/files/HDDV_1_ab.docx", request_attachment="/private/files/HDDV_1_ab.docx",
                 signed_file="/private/files/ky.pdf",
                 acceptances=[Row(bbnt_file="/private/files/BBNT_1.docx", signed_file="/private/files/bbnt ky.pdf")])
        seen = {}
        STATE["get_all"]["File"] = lambda f, kw: seen.setdefault("f", f) and ["F-dup-1", "F-dup-2"]
        sets = []
        sys.modules["frappe"].db.set_value = lambda dt_, n, f, v=None, **k: sets.append((dt_, n, f, v))
        a.lock_pii_files(d)
        self.assertEqual(sorted(seen["f"]["file_url"][1]), sorted(["/private/files/HDDV_1_ab.docx", "/private/files/ky.pdf",
                                                                   "/private/files/BBNT_1.docx", "/private/files/bbnt ky.pdf"]))
        self.assertEqual(sets, [("File", "F-dup-1", "owner", "Administrator"), ("File", "F-dup-2", "owner", "Administrator")])
        ctl = _read("doctype/ec_contract_review_request/ec_contract_review_request.py")
        self.assertIn("def on_change(self):", ctl)
        self.assertIn("kol_access.lock_pii_files", ctl)

    def test_tao_creator_khong_lach_chan_trung_bang_disabled(self):
        from test_creators_service import EXISTING, FakeRepo
        from ecentric_workspace.approval_center.shared.creators.service import CreatorError, CreatorService
        repo = FakeRepo([EXISTING], {"ke.toan@ec": ["EC Finance"]})
        with self.assertRaises(CreatorError):
            CreatorService(repo).create("an@ec", {"supplier_name": "Khác", "ec_cr_type": "Cá nhân",
                                                  "ec_cr_cccd": EXISTING["ec_cr_cccd"], "ec_bank_account_no": "999",
                                                  "ec_bank_name": "VCB", "disabled": "0"}, confirm_soft=True)
        from ecentric_workspace.approval_center.shared.creators import domain
        rows = [{"name": "SUP-2", "ec_cr_type": "Cá nhân", "ec_bank_account_no": "0011223344"}]
        self.assertTrue(domain.classify_duplicates({"ec_cr_type": "Công ty", "ec_bank_account_no": "0011223344",
                                                    "disabled": "0"}, rows)["hard"])

    def test_dien_stk_chi_cho_nguoi_duoc_thay(self):
        src = _read("features/contract_review/application/kol_funding.py")
        i = src.index("def fill_payment")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('may_see = funding_approved(name) and kol_access.can_download_full(doc, frappe.session.user)', body)

    def test_phieu_cu_contract_type_rong_van_duoc_xet(self):
        api = _read("features/contract_review/controllers/api.py")
        self.assertIn('rows = [r for r in rows if r.get("contract_type") != "KOL/KOC / Creator (EC)"]', api)
        p397 = _read("patches/p397_chu_ky_duyet_hop_dong_tep.py")
        self.assertNotIn('"contract_type": ["!=", _KOL]', p397)


# ----------------------------------------------------------------------------- QC vong 4 17/11
class QcVong4(unittest.TestCase):
    def test_luc_gui_chua_co_stk_thi_stk_them_sau_phai_xac_nhan(self):
        a = _access()
        d = _kol()
        a.snapshot_payee(d, {"ec_bank_account_no": "", "ec_bank_name": ""})
        self.assertEqual(d["kol_payee_fp"], a.NO_ACCOUNT)
        self.assertFalse(a.payee_changed(d, {"ec_bank_account_no": "", "ec_bank_name": ""}))
        self.assertTrue(a.payee_changed(d, {"ec_bank_account_no": "123", "ec_bank_name": "VCB"}))

    def test_ngoai_le_tool_cu_khong_lach_bang_chu_thuong(self):
        _fresh("req@ec")
        fu = importlib.import_module(P + "kol_funding")
        STATE["get_all"][CR] = lambda f, kw: [Row(name="EC-CTR-9", contract_no="05112026/HDDV/ECENTRIC-NTP.FCV",
                                                  approval_request="AR-9")]
        STATE["values"][("EC Approval Request", "AR-9")] = "Approved"
        with self.assertRaises(Throw):
            fu.legacy_contract_ref({"has_purchase_request": "No",
                                    "no_purchase_request_reason": "05112026/hddv/ecentric-ntp.fcv"})

    def test_coc_hieu_luc_dung_chung_cho_tran_va_thong_bao(self):
        _s, _v, acc, _f = _fresh("fin@ec")
        d = _kol(signing_status="Đã ký đủ", advance_amount=3_000_000, payable_amount=10_000_000,
                 signed_at="2026-11-18 09:00:00", kol_closed_at="2026-11-17 10:00:00")
        self.assertEqual(acc.effective_advance(d), 0.0)
        src = _read("features/contract_review/application/kol_acceptance.py")
        self.assertIn('"advance": effective_advance(doc)', src)

    def test_khong_doi_loai_khi_da_tao_hop_dong_kol(self):
        s, _v, _a, _f = _fresh("req@ec")
        d = Doc(doctype=CR, name="CR-5", contract_type="Sales / Bán ra (EC)",
                contract_file="/private/files/HDDV_1_ab.docx", acceptances=[], generated_template="TPL-1")
        s.esign_flow.apply_default = lambda doc: None
        s.esign_flow.clean_labor = lambda doc: None
        with self.assertRaises(Throw) as cm:
            s.prepare_draft(d)
        self.assertIn("không đổi sang loại", str(cm.exception))

    def test_nhan_ban_bo_hop_dong_sinh_tu_mau_cua_phieu_cu(self):
        src = _read("features/contract_review/application/kol_service.py")
        i = src.index("def prepare_draft")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('kol_access.foreign_generated(doc, doc.get("request_attachment"))', body)

    def test_da_thanh_ly_van_chi_xoa_dot_nhap_cuoi(self):
        _s, _v, acc, _f = _fresh("fin@ec")
        STATE["roles"]["fin@ec"] = ["EC Finance"]
        d = _kol(kol_closed_at="2026-11-17 10:00:00", requested_by="fin@ec", owner="fin@ec")
        d["acceptances"] = [Row(name="r1", idx=1, status="Nháp", amount=1, bbnt_file=None),
                            Row(name="r2", idx=2, status="Đã gửi ký", amount=1, bbnt_file=None)]
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        with self.assertRaises(Throw) as cm:
            acc.delete_acceptance("CR-1", "fin@ec", "r1")
        self.assertIn("cuối cùng", str(cm.exception))


class QcVongCuoi(unittest.TestCase):
    """QC vong cuoi 17/11: nhan dien tep HE THONG sinh khong chi dua vao ten tep."""

    def test_phieu_loai_khac_co_tep_ten_hddv_van_luu_duoc(self):
        s, _v, _a, _f = _fresh("req@ec")
        s.esign_flow.apply_default = lambda doc: None
        s.esign_flow.clean_labor = lambda doc: None
        d = Doc(doctype=CR, name="CR-6", contract_type="Purchase / Mua vào (EC)",
                contract_file="/private/files/HDDV_x.pdf", acceptances=[])
        STATE["values"][(CR, "CR-6")] = lambda field, as_dict: {"contract_type": "Purchase / Mua vào (EC)"}
        STATE["get_all"]["File"] = lambda f, kw: ["[Đối chứng] HDDV_x.docx"]
        s.prepare_draft(d)                       # khong nem loi

    def test_phieu_dang_luu_la_kol_co_tep_he_thong_thi_khong_doi_loai(self):
        s, _v, _a, _f = _fresh("req@ec")
        s.esign_flow.apply_default = lambda doc: None
        s.esign_flow.clean_labor = lambda doc: None
        d = Doc(doctype=CR, name="CR-7", contract_type="Sales / Bán ra (EC)", contract_file=None, acceptances=[])
        STATE["values"][(CR, "CR-7")] = lambda field, as_dict: {"contract_type": "KOL/KOC / Creator (EC)"}
        STATE["get_all"]["File"] = lambda f, kw: ["HDDV_7_ab12cd34.docx"]
        with self.assertRaises(Throw):
            s.prepare_draft(d)

    def test_tep_cua_phieu_khac_moi_bo_tep_vua_tai_hoac_da_gan_thi_giu(self):
        a = _access("req@ec")
        d = Doc(doctype=CR, name="CR-8")
        STATE["get_all"]["File"] = lambda f, kw: [{"attached_to_doctype": CR, "attached_to_name": "CR-OLD",
                                                   "owner": "Administrator"}]
        self.assertTrue(a.foreign_generated(d, "/private/files/HDDV_1_ab12cd34.docx"))
        STATE["get_all"]["File"] = lambda f, kw: [{"attached_to_doctype": None, "attached_to_name": None,
                                                   "owner": "req@ec"}]
        self.assertFalse(a.foreign_generated(d, "/private/files/HDDV_hop_dong_creator.pdf"))
        STATE["get_all"]["File"] = lambda f, kw: [{"attached_to_doctype": CR, "attached_to_name": "CR-8",
                                                   "owner": "req@ec"}]
        self.assertFalse(a.foreign_generated(d, "/private/files/HDDV_hop_dong_creator.pdf"))
        self.assertFalse(a.foreign_generated(d, "/private/files/hop dong.pdf"))

    def test_mau_creator_ten_hddv_nguoi_duyet_van_thay(self):
        a = _access("appr@ec")
        b = _biz()
        b.update({"request_type": "Template from partner / Mẫu theo khung đối tác", "contract_file": None,
                  "request_attachment": "/private/files/HDDV_hop_dong_creator.pdf", "requested_by": "req@ec"})
        a.redact_business(b)
        self.assertEqual(b["request_attachment"], "/private/files/HDDV_hop_dong_creator.pdf")
        out = a.redact_attachments([{"file_url": "/private/files/HDDV_hop_dong_creator.pdf",
                                     "file_name": "HDDV_hop_dong_creator.pdf", "owner": "req@ec"}], b)
        self.assertEqual(len(out), 1)

    def test_mau_ec_nguoi_duyet_van_bi_an(self):
        a = _access("appr@ec")
        b = _biz()
        b.update({"request_type": "Template from EC / Mẫu theo khung EC", "requested_by": "req@ec",
                  "request_attachment": b["contract_file"]})
        a.redact_business(b)
        self.assertIsNone(b["request_attachment"])
        self.assertIsNone(b["contract_file"])

    def test_tim_hop_dong_goc_khong_loc_sql_bang_khac(self):
        src = _read("features/contract_review/controllers/api.py")
        i = src.index("def search_previous_contracts")
        body = src[i:src.index("\n@frappe.whitelist", i + 10) if "\n@frappe.whitelist" in src[i + 10:] else len(src)]
        self.assertNotIn('["contract_type", "!="', body)
        self.assertIn('r.get("contract_type") != "KOL/KOC / Creator (EC)"', body)


if __name__ == "__main__":
    unittest.main()


class QcTachNhiemVu18_11(unittest.TestCase):
    """QC 18/11 (sau E2E): nguoi doi STK / nguoi lap phieu khong tu xac nhan; khong tu mo lai thanh ly."""

    def _setup(self, changers=(), supplier_mod=None):
        a = _access("fin@ec", {"fin@ec": ["EC Finance"], "kt2@ec": ["EC Finance"], "req@ec": ["EC Finance"]})
        old = {"ec_bank_account_no": "111", "ec_bank_name": "VCB"}
        new = {"ec_bank_account_no": "222", "ec_bank_name": "VCB"}
        d = _kol(submitted_at="2026-11-18 10:00:00")
        a.snapshot_payee(d, old)
        STATE["values"][("EC Approval Request", "AR-1")] = "Approved"
        ks = importlib.import_module(P + "kol_service")
        ks.creator_row = lambda n: new
        STATE["get_all"]["Comment"] = lambda f, kw: [{"owner": u, "comment_email": u} for u in changers]
        STATE["values"][("Supplier", "SUP-1")] = (
            lambda field, as_dict: (supplier_mod or {}) if isinstance(field, (list, tuple)) else
            ("owner@ec" if field == "owner" else None))
        sys.modules["frappe"].db.set_value = lambda *x, **k: None
        return a, d

    def test_nguoi_doi_stk_khong_tu_xac_nhan(self):
        a, d = self._setup(changers=("fin@ec",))
        self.assertEqual(a.payee_changers(d), {"fin@ec"})
        self.assertFalse(a.can_confirm_payee(d, "fin@ec"))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.confirm_payee("CR-1", "fin@ec")
        self.assertTrue(a.can_confirm_payee(d, "kt2@ec"))
        self.assertEqual(a.confirm_payee("CR-1", "kt2@ec"), {"ok": True, "changed": True})
        self.assertTrue(any("người đổi: fin@ec" in c for c in STATE["comments"]))

    def test_nguoi_lap_la_ke_toan_khong_tu_xac_nhan(self):
        a, d = self._setup(changers=("owner@ec",))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.confirm_payee("CR-1", "req@ec")

    def test_sua_tren_desk_khong_binh_luan_lay_nguoi_sua_supplier(self):
        a, d = self._setup(changers=(), supplier_mod={"modified_by": "fin@ec", "modified": "2026-11-18 11:00:00"})
        self.assertEqual(a.payee_changers(d), {"fin@ec"})
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.confirm_payee("CR-1", "fin@ec")

    def test_sua_supplier_truoc_moc_khong_tinh(self):
        a, d = self._setup(changers=(), supplier_mod={"modified_by": "fin@ec", "modified": "2026-11-18 09:00:00"})
        self.assertEqual(a.payee_changers(d), set())

    def test_nguoi_lap_khong_tu_mo_lai_thanh_ly(self):
        a = _access("req@ec", {"req@ec": ["EC Finance"], "fin@ec": ["EC Finance"]})
        sys.modules["frappe"].db.set_value = lambda *x, **k: None
        _kol(kol_closed_at="2026-11-17 10:00:00", kol_close_reason="x")
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.reopen_contract("CR-1", "req@ec", "nham")
        a.reopen_contract("CR-1", "fin@ec", "thanh ly nham")

    def test_trang_an_nut_xac_nhan_voi_chinh_minh_va_xoa_nhap(self):
        src = _read("features/contract_review/ui/main_section.html")
        self.assertIn("x.can_verify_sign?", src)
        self.assertIn("r.can_verify&&r.status===", src)
        self.assertIn("x.can_confirm_payee?", src)
        self.assertIn("function doDeleteDraft", src)
        self.assertIn(">Xoá bản nháp</button>", src)
        pr = _read("features/payment_request/ui/main_section.html")
        self.assertIn("function doDeleteDraft", pr)
        svc = _read("features/contract_review/application/kol_service.py")
        self.assertIn('"can_verify_sign"', svc)
        self.assertIn('r["can_verify"]', svc)
        acc = _read("features/contract_review/application/kol_acceptance.py")
        self.assertIn("tạo BBNT đợt", acc)


class QcNganHangTheoCreator18_11(unittest.TestCase):
    def test_dntt_lay_ten_ngan_hang_tu_creator(self):
        src = _read("features/contract_review/application/kol_funding.py")
        j = src.index("def _check_payee")
        body = src[j:]
        self.assertIn('bank = (creator.get("ec_bank_name") or "").strip()', body)
        self.assertIn("pr.account_bank = bank", body)
        self.assertLess(body.index("typed != stored"), body.index("pr.account_bank = bank"))
        qs = _read("shared/requests/query_service.py")
        self.assertIn('"previous_status", "new_status", "related_user"]', qs)


class QcHopDongToolCu20_11(unittest.TestCase):
    """PO 20/11: DNTT ngoai le HD tool cu luu so HD + trang hien cac DNTT khac cung so."""

    def test_luu_so_hd_cu_len_phieu(self):
        _fresh("req@ec")
        fu = importlib.import_module(P + "kol_funding")
        STATE["get_all"][CR] = lambda f, kw: []
        pr = {"has_purchase_request": "No",
              "no_purchase_request_reason": "đợt 2 HĐ 05112026/HDDV/ECENTRIC-NTP.FCV, trùng 05112026/hddv/ecentric-ntp.fcv"}
        self.assertTrue(fu.legacy_contract_ref(pr))
        self.assertEqual(pr["ec_legacy_contract_no"], "05112026/HDDV/ECENTRIC-NTP.FCV")
        self.assertEqual(fu.old_numbers("a 05112026/HDDV/A.B va HDDV/09102026/DMG-ECENTRIC-X"),
                         ["05112026/HDDV/A.B", "HDDV/09102026/DMG-ECENTRIC-X"])
        # 23/11: so tool cu dang 4 chu so (EC-PAYR-2026-00749)
        self.assertEqual(fu.old_numbers("theo HĐHT số 2509/HDDV/ECENTRIC-BK-VITA"),
                         ["2509/HDDV/ECENTRIC-BK-VITA"])
        self.assertEqual(fu.old_numbers("so 123/HDDV/X va 2025 HDDV"), [])

    def test_trang_canh_bao_cac_dntt_khac_cung_so(self):
        _fresh("appr@ec")
        fu = importlib.import_module(P + "kol_funding")
        rows = [Row(name="PR-2", payment_amount=10000000, approval_request="AR-2", ec_legacy_contract_no="05112026/HDDV/A.B"),
                Row(name="PR-3", payment_amount=7000000, approval_request="AR-3", ec_legacy_contract_no="05112026/HDDV/A.B, 01012025/HDDV/C.D"),
                Row(name="PR-4", payment_amount=9000000, approval_request="AR-4", ec_legacy_contract_no="05112026/HDDV/A.BC"),
                Row(name="PR-5", payment_amount=5000000, approval_request="AR-5", ec_legacy_contract_no="05112026/HDDV/A.B")]
        STATE["get_all"]["EC Payment Request"] = lambda f, kw: list(rows)
        STATE["values"][("EC Approval Request", "AR-2")] = "Approved"
        STATE["values"][("EC Approval Request", "AR-3")] = "Pending"
        STATE["values"][("EC Approval Request", "AR-5")] = "Cancelled"
        v = fu.legacy_view({"name": "PR-1", "ec_legacy_contract_no": "05112026/HDDV/A.B"})
        self.assertEqual([x["name"] for x in v["others"]], ["PR-2", "PR-3"])     # A.BC khac so; PR-5 da huy
        self.assertEqual(v["others_total"], 17000000)
        self.assertIsNone(fu.legacy_view({"name": "PR-1", "ec_legacy_contract_no": ""}))

    def test_noi_day_service_va_trang(self):
        svc = _read("features/payment_request/application/service.py")
        self.assertIn('doc.ec_legacy_contract_no = None', svc)
        self.assertIn('out["legacy_contract"] = legacy', svc)
        fun = _read("features/payment_request/application/funding.py")
        self.assertIn('"legacy_view_fn": _KOL + "legacy_view"', fun)
        page = _read("features/payment_request/ui/main_section.html")
        self.assertIn("function legacyKolHTML(det)", page)
        self.assertIn("+legacyKolHTML(det)+", page)
        import json
        meta = json.loads(_read("doctype/ec_payment_request/ec_payment_request.json"))
        self.assertIn("ec_legacy_contract_no", meta["field_order"])
        self.assertIn("p420_dntt_so_hd_tool_cu", open(os.path.join(HERE, "..", "..", "..", "patches.txt")).read())


class PatchesTxtModulesExist(unittest.TestCase):
    """Moi dong patches.txt phai tro toi mot tep co that - doi so patch ma quen sua patches.txt thi migrate
    dung giua chung (bai hoc 19/11: p417 -> p419)."""

    def test_moi_dong_co_tep(self):
        app = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        miss = []
        for line in open(os.path.join(app, "patches.txt"), encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith(("[", "#", "execute:")):
                continue
            rel = s.split()[0].replace("ecentric_workspace.", "", 1).replace(".", os.sep) + ".py"
            if not os.path.exists(os.path.join(app, rel)):
                miss.append(s)
        self.assertEqual(miss, [])
