# Copyright (c) 2026, eCentric and contributors
"""PR-I (24/11/2026, thu that EC-CTR-2026-00134): o ky DOI TAC + loi cong CMC noi ro.

  1. scts_client: AddDocument 5xx (khong phai het han muc) -> van MO HO nhung thong bao loi mang
     cau giai thich cua cong DA LAM SACH (bo base64 / token / Bearer); 4xx cung vay.
  2. scts.create_document co ExternalHandlers: them muc Signatures cho vung "Doi tac ky" dat
     theo moc [[KY_BEN_B]] (giong het hinh dang muc cua o ky ERP); thieu moc -> tu choi ro rang;
     mau khong co vung doi tac -> bo qua; tep can ky chia se cho doi tac.
     KHONG co doi tac (DNTT) -> payload y nhu cu.
  3. pdf_markers: o ky mac dinh 180x100pt.
  4. placement_service.auto_place: ho so co doi tac ma tep thieu [[KY_BEN_B]] -> canh bao.
Chay voi tep PDF that (make_pdf cua test_esign_tu_dat_o_ky) qua adapter that + transport gia.
"""
import io
import json
import sys
import types
import unittest
from datetime import datetime, timedelta

_fr = sys.modules.get("frappe")
if not (_fr and getattr(_fr, "utils", None)
        and getattr(_fr.utils, "now_datetime", None)
        and getattr(_fr, "get_doc", None)):
    fr = types.ModuleType("frappe")
    fr._ = lambda x: x
    fr.conf = {}
    fr.db = types.SimpleNamespace(set_value=lambda *a, **k: None,
                                  get_value=lambda *a, **k: None)
    fr.get_doc = lambda *a, **k: types.SimpleNamespace(save=lambda **kw: None)
    fr.session = types.SimpleNamespace(user="test@x")
    fr.log_error = lambda *a, **k: None
    fr.flags = types.SimpleNamespace()      # module khac chay sau trong cung lan (payload_budget)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 8, 22, 12, 0, 0)
    utils.get_datetime = lambda v: (
        v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))
    utils.add_to_date = lambda d, **kw: d + timedelta(minutes=kw.get("minutes", 0),
                                                      days=kw.get("days", 0))
    utils.cint = lambda v: int(v or 0)
    utils.flt = lambda v: float(v or 0)
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: "tok-cached"
    utils.password = pw
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.utils.password"] = pw

sys.path.insert(0, ".")
from ecentric_workspace.platform.esign.providers import scts as scts_mod  # noqa: E402
from ecentric_workspace.platform.esign.providers.scts import SctsAdapter  # noqa: E402
from ecentric_workspace.platform.esign.providers.scts_client import SctsClient  # noqa: E402
from ecentric_workspace.platform.esign.providers.base import ProviderError  # noqa: E402
from ecentric_workspace.approval_center.tests.standalone import test_esign_tu_dat_o_ky as T  # noqa: E402

if not getattr(sys.modules["frappe"], "log_error", None):
    sys.modules["frappe"].log_error = lambda *a, **k: None


class Resp(object):
    def __init__(self, status, data=None, text=None):
        self.status_code = status
        self._data = data
        self.text = text if text is not None else json.dumps(data)

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


B64 = "JVBERi0xLjQKJcOkw7zDtsOfCjIgMCBvYmoKPDwvTGVuZ3RoIDMgMCBSL0ZpbHRlci9GbGF0ZURlY29kZT4+"


class TestLoiCong(unittest.TestCase):
    def _client(self, resp):
        return SctsClient(base_url="https://x", transport=lambda *a, **k: resp, timeout=5)

    def test_500_mo_ho_kem_cau_giai_thich_da_lam_sach(self):
        c = self._client(Resp(500, {"success": False,
                                    "message": "Lỗi hệ thống: Object reference not set. PdfBase64 "
                                               + B64 + " Bearer abc.def.ghi"}))
        with self.assertRaises(ProviderError) as cm:
            c.add_document({}, "TOK")
        e = cm.exception
        self.assertEqual(e.code, "scts_create_outcome_unknown")
        self.assertTrue(getattr(e, "ambiguous", False))
        msg = str(e.args) + str(getattr(e, "message", ""))
        self.assertIn("Object reference not set", msg)
        self.assertNotIn(B64, msg)
        self.assertNotIn("abc.def.ghi", msg)

    def test_500_het_han_muc_giu_nguyen(self):
        c = self._client(Resp(500, {"success": False,
                                    "message": "Lỗi hệ thống: Đã vượt hạn mức sử dụng 1132/1100"}))
        with self.assertRaises(ProviderError) as cm:
            c.add_document({}, "TOK")
        self.assertEqual(cm.exception.code, "scts_create_quota_exceeded")

    def test_4xx_kem_errors(self):
        c = self._client(Resp(400, {"title": "One or more validation errors occurred.",
                                    "errors": {"ExternalHandlers[0].IdentityNumber":
                                               ["The field is required."]}}))
        with self.assertRaises(ProviderError) as cm:
            c.add_document({}, "TOK")
        self.assertEqual(cm.exception.code, "scts_create_rejected_400")
        self.assertIn("IdentityNumber", str(cm.exception.args))

    def test_che_cccd_sdt_email(self):
        """QC 24/11: cau loi cong lap lai du lieu doi tac -> che truoc khi vao error_summary."""
        d = SctsClient._provider_error_detail(Resp(500, {
            "success": False,
            "message": "Doi tac CCCD 079012345678, SDT 0901234567, email hoan+kol@gmail.com loi"}))
        self.assertNotIn("079012345678", d)
        self.assertNotIn("0901234567", d)
        self.assertNotIn("hoan+kol@gmail.com", d)
        self.assertIn("***@***", d)
        self.assertIn("loi", d)

    def test_khoa_base64_khong_lam_safe_error_giau_ca_cau(self):
        # Nap sanitize bang exec (KHONG vao sys.modules - khong lam ban module test khac).
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        g = {}
        exec(compile(io.open(os.path.join(here, "..", "..", "..", "platform", "esign",
                                          "sanitize.py"), encoding="utf-8").read(),
                     "sanitize.py", "exec"), g)
        safe_error = g["safe_error"]
        c = self._client(Resp(400, {"title": "One or more validation errors occurred.",
                                    "errors": {"Documents[0].PdfBase64": ["The field is required."],
                                               "ExternalHandlers[0].Dob": ["Invalid date."]}}))
        with self.assertRaises(ProviderError) as cm:
            c.add_document({}, "TOK")
        txt = safe_error(cm.exception)
        self.assertNotIn("withheld", txt)
        self.assertIn("Dob", txt)
        self.assertNotIn("PdfBase64", txt)

    def test_body_html_hoac_rong(self):
        d = SctsClient._provider_error_detail(Resp(502, None, text="<html>Bad gateway</html>"))
        self.assertEqual(d, "")
        self.assertEqual(SctsClient._provider_error_detail(Resp(500, None, text="")), "")


# --------------------------------------------------------------------------- create_document
AREAS = [{"signatureId": "15311B8F", "title": "Đối tác ký", "role": "doitac",
          "signatureType": "position", "keyword": "", "margin": 0, "canBeSigned": True, "added": 0},
         {"signatureId": "29CF1970", "title": "Đơn vị ký", "role": "chinh",
          "signatureType": "position", "keyword": "", "margin": 0, "canBeSigned": True, "added": 0}]
PDF_AB = T.make_pdf([T.BODY + T.MARK_B])            # co moc KY_BEN_B o trang 1
PDF_NO_B = T.make_pdf([T.BODY])
HANDLER = [{"full_name": "Hoan", "email": "hoan+kol@gmail.com", "identity": "0790",
            "sign_type": "image"}]


def _run(files, placements, handlers=None, areas=AREAS):
    calls = []

    def transport(method, url, headers=None, json_body=None, **kw):
        calls.append((url, json_body))
        if url.endswith("/api/AddDocument/ConvertPdfFile"):
            return Resp(200, {"data": {"jsonData": json.dumps(areas)}})
        return Resp(200, {"success": True, "data": "DOC-1"})
    a = SctsAdapter.__new__(SctsAdapter)
    a._client = SctsClient(base_url="https://x", transport=transport, timeout=5)
    a._with_auth = lambda fn: fn("TOKEN")
    a.assert_partner_sign_types_available = lambda h: None
    ctx = {"doc_code": "EC-CTR-1", "title": "t", "amount": 1, "deadline": "",
           "workflow_definition_id": "WF09", "document_type_id": "DT", "company_id": "EC",
           "department_id": "D", "document_template_id": "", "files": files,
           "placements": placements, "external_handlers": handlers}
    a.create_document(ctx)
    body = [b for u, b in calls if u.endswith("/api/AddDocument")][0]
    return body


def _file(content, dsf="DSF1", signable=True):
    return {"order": 0, "file_dsf": dsf, "name": "hd.pdf", "content": content,
            "can_be_signed": signable, "is_supporting_document": not signable,
            "share_with_partner": False}


CEO = {"signature_file": "DSF1", "page_index": 1, "x": 99.0, "y": 302.0, "width": 180,
       "height": 120, "level_no": 5, "page_height": 841.89, "scts_role_title": "Đơn vị ký"}


class TestODoiTac(unittest.TestCase):
    def test_khong_doi_tac_payload_nhu_cu(self):
        body = _run([_file(PDF_AB)], [dict(CEO)], handlers=None)
        doc = body["Documents"][0]
        self.assertEqual([s["title"] for s in doc["Signatures"]], ["Đơn vị ký"])
        self.assertFalse(doc["IsSharedWithPartner"])
        self.assertEqual(body["ExternalHandlers"], [])

    def test_co_doi_tac_them_o_theo_moc_va_chia_se(self):
        body = _run([_file(PDF_AB)], [dict(CEO)], handlers=HANDLER)
        doc = body["Documents"][0]
        self.assertEqual([s["title"] for s in doc["Signatures"]], ["Đơn vị ký", "Đối tác ký"])
        ceo, pt = doc["Signatures"]
        self.assertEqual(set(ceo), set(pt), "muc doi tac PHAI cung hinh dang voi muc ERP")
        self.assertEqual(pt["signatureId"], "15311B8F")
        self.assertEqual(pt["role"], "doitac")
        self.assertEqual(pt["pageIndex"], 1)
        # vi tri: moc KY_BEN_B tai x=360 (BT 360 460) -> o canh trai moc, 180x100
        box = scts_mod._partner_box(PDF_AB)
        self.assertEqual((box["width"], box["height"]), (180.0, 100.0))
        exp = scts_mod.to_provider_box(box["x"], max(0.0, box["page_height"] - box["y"] - 100.0),
                                       180.0, 100.0)
        self.assertEqual((pt["x"], pt["y"], pt["Width"], pt["Height"]),
                         (exp["x"], exp["y"], exp["w"], exp["h"]))
        self.assertTrue(doc["IsSharedWithPartner"])
        self.assertEqual(len(body["ExternalHandlers"]), 1)

    def test_muc_doi_tac_giong_het_muc_erp_cung_hinh_hoc(self):
        """Cung toa do -> _signature_entry cho ra DUNG muc create_document dung cho o ERP."""
        body = _run([_file(PDF_AB)], [dict(CEO)], handlers=None)
        ceo = body["Documents"][0]["Signatures"][0]
        mine = scts_mod._signature_entry(AREAS[1], 1, 99.0, 302.0, 180, 120, 841.89)
        self.assertEqual(mine, ceo)

    def test_thieu_moc_ky_ben_b_thi_tu_choi_ro(self):
        with self.assertRaises(ProviderError) as cm:
            _run([_file(PDF_NO_B)], [dict(CEO)], handlers=HANDLER)
        self.assertEqual(cm.exception.code, "partner_position_missing")
        self.assertFalse(cm.exception.retryable)

    def test_mau_khong_co_vung_doi_tac_thi_bo_qua(self):
        body = _run([_file(PDF_NO_B)], [dict(CEO)], handlers=HANDLER, areas=[AREAS[1]])
        self.assertEqual([s["title"] for s in body["Documents"][0]["Signatures"]], ["Đơn vị ký"])

    def test_tep_phu_khong_them_o_doi_tac(self):
        f2 = dict(_file(PDF_NO_B, dsf="DSF2", signable=False), order=1, name="phu.pdf")
        body = _run([_file(PDF_AB), f2], [dict(CEO)], handlers=HANDLER)
        self.assertEqual(len(body["Documents"][0]["Signatures"]), 2)
        self.assertEqual(body["Documents"][1]["Signatures"], [])
        self.assertFalse(body["Documents"][1]["IsSharedWithPartner"])

    def test_khong_o_erp_van_lay_vung_khi_co_doi_tac(self):
        body = _run([_file(PDF_AB)], [], handlers=HANDLER)
        self.assertEqual([s["title"] for s in body["Documents"][0]["Signatures"]], ["Đối tác ký"])

    def test_nhieu_moc_lay_moc_dau_nhu_ky_ben_a(self):
        """QC 24/11: CUNG luat voi [[KY_BEN_A]] (moc dau tien) - hai ben ky cung mot khoi."""
        pdf = T.make_pdf([T.BODY + T.MARK_B, T.BODY + T.MARK_B])
        self.assertEqual(scts_mod._partner_box(pdf)["page_index"], 1)

    def test_nhieu_tep_mot_tep_thieu_moc_van_gui(self):
        """QC 24/11: chi tu choi khi KHONG tep nao dat duoc o doi tac."""
        f2 = dict(_file(PDF_NO_B, dsf="DSF2"), order=1, name="phu-luc.pdf")
        body = _run([_file(PDF_AB), f2], [dict(CEO)], handlers=HANDLER)
        self.assertEqual([s["title"] for s in body["Documents"][0]["Signatures"]],
                         ["Đơn vị ký", "Đối tác ký"])
        self.assertEqual(body["Documents"][1]["Signatures"], [])

    def test_tat_ca_thieu_moc_noi_ro_ten_tep(self):
        f2 = dict(_file(PDF_NO_B, dsf="DSF2"), order=1, name="phu-luc.pdf")
        with self.assertRaises(ProviderError) as cm:
            _run([_file(PDF_NO_B), f2], [dict(CEO)], handlers=HANDLER)
        self.assertEqual(cm.exception.code, "partner_position_missing")
        msg = str(cm.exception.args)
        self.assertIn("hd.pdf", msg)
        self.assertIn("phu-luc.pdf", msg)

    def test_ly_do_moc_bi_bo_duoc_noi_ra(self):
        orig = scts_mod.__dict__.get("_partner_box")
        import ecentric_workspace.platform.esign.pdf_markers as pm
        real = pm.analyze
        pm.analyze = lambda c: {"markers": [], "skipped": [
            {"name": "KY_BEN_B", "page_index": 3, "reason": "rotated_page:90"}]}
        try:
            why = []
            self.assertIsNone(orig(b"%PDF-x", reasons=why))
            self.assertEqual(why, ["trang 3: rotated_page:90"])
        finally:
            pm.analyze = real

    def test_vung_doi_tac_da_co_o_erp_thi_khong_trung(self):
        ceo_as_partner = dict(CEO, scts_role_title="Đối tác ký")
        body = _run([_file(PDF_AB)], [ceo_as_partner], handlers=HANDLER)
        sig_ids = [s["signatureId"] for s in body["Documents"][0]["Signatures"]]
        self.assertEqual(sig_ids, ["15311B8F"])


class TestHopBoxMacDinh(unittest.TestCase):
    def test_100pt(self):
        from ecentric_workspace.platform.esign import pdf_markers as pm
        self.assertEqual((pm.BOX_W, pm.BOX_H), (180.0, 100.0))


class TestCanhBaoAutoPlace(unittest.TestCase):
    def test_canh_bao_duoc_boc_try_va_chi_khi_ho_so_co_doi_tac(self):
        import io
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        src = io.open(os.path.join(here, "..", "..", "..", "platform", "esign",
                                   "placement_service.py"), encoding="utf-8").read()
        i = src.index("def auto_place(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('m.get("name") == "KY_BEN_B"', body)
        self.assertIn("_partner_expected(cur)", body)
        self.assertIn("except Exception:", body[body.index("KY_BEN_B"):])


if __name__ == "__main__":
    unittest.main()
