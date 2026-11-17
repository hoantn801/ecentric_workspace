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
import json
import os
import sys
import types
import unittest

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Row, Throw, _fresh  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
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
        self.assertFalse(a.can_download_full(b, "req@ec"))             # nguoi lap phieu
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
        self.assertEqual(b, _biz())
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
        self.assertTrue(any("fin@ec" in c and "HDDV_17112026_ab12cd34.docx" in c for c in STATE["comments"]))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.download_file("CR-1", "/private/files/HDDV_17112026_ab12cd34.docx", "req@ec")

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
        self.assertIn("attachments = []", q)                 # loi redactor -> khong tra tep nao (fail-closed)

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
        self.assertIn("Hợp đồng mới", str(cm.exception))

    def test_trang_khoa_va_tu_doi_ve_moi(self):
        html = _read("features/contract_review/ui/main_section.html")
        self.assertIn('if(d.request_kind==="Existing" && KOL.isKol(d)) errs.request_kind=', html)
        self.assertIn('if(state.draft.request_kind==="Existing"){ state.draft.request_kind="New";', html)


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
        a.snapshot_payee(d, old)
        self.assertFalse(a.payee_changed(d, old))
        self.assertTrue(a.payee_changed(d, new))
        ks = importlib.import_module(P + "kol_service")
        ks.creator_row = lambda n: new
        sets = []
        sys.modules["frappe"].db.set_value = lambda dt_, n, f, v=None, **k: sets.append((f, v))
        with self.assertRaises(sys.modules["frappe"].PermissionError):
            a.confirm_payee("CR-1", "req@ec")
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
        sys.path.insert(0, HERE)
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
        self.assertIn('funding.required_source(category)', svc)

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
        self.assertIn('f.method="POST"', html)
        self.assertIn('"kol_download_file"', html)
        self.assertNotIn('href="\'+esc(b.contract_file)', html)
        self.assertNotIn('href="\'+esc(r.bbnt_file)', html)
        self.assertNotIn('href="\'+esc(b.signed_file)', html)


if __name__ == "__main__":
    unittest.main()
