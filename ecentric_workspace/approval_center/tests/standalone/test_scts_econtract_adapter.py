# Copyright (c) 2026, eCentric and contributors
"""STANDALONE (no bench) contract tests for the SCTS eContract adapter update (2026-08-22).
Stubs the frappe module + injects a mock transport, then drives the REAL SctsClient/SctsAdapter
against the exact request/response samples published at econtract.scts.com.vn/API.
Run:  python3 ecentric_workspace/approval_center/tests/standalone/test_scts_econtract_adapter.py
"""
import base64
import json
import sys
import types
import unittest
from datetime import datetime, timedelta

# ---------------- frappe stub (adapter imports frappe + frappe.utils) ----------------
frappe = types.ModuleType("frappe")
frappe._ = lambda x: x
frappe.db = types.SimpleNamespace(set_value=lambda *a, **k: None,
                                  get_value=lambda *a, **k: None)
frappe.get_doc = lambda *a, **k: types.SimpleNamespace(save=lambda **kw: None)
frappe.session = types.SimpleNamespace(user="test@x")
utils = types.ModuleType("frappe.utils")
utils.now_datetime = lambda: datetime(2026, 8, 22, 12, 0, 0)
utils.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
utils.add_to_date = lambda d, **kw: d + timedelta(minutes=kw.get("minutes", 0),
                                                  days=kw.get("days", 0))
pw = types.ModuleType("frappe.utils.password")
pw.get_decrypted_password = lambda *a, **k: "tok-cached"
utils.password = pw
frappe.utils = utils
sys.modules["frappe"] = frappe
sys.modules["frappe.utils"] = utils
sys.modules["frappe.utils.password"] = pw

sys.path.insert(0, ".")
from ecentric_workspace.platform.esign.providers.scts import SctsAdapter  # noqa: E402
from ecentric_workspace.platform.esign.providers.scts_client import SctsClient  # noqa: E402


class Resp:
    def __init__(self, status, body=None, ct="application/json"):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Type": ct}
        self.content = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        self.text = "" if isinstance(body, bytes) else json.dumps(body or {})
    def json(self):
        if isinstance(self._body, bytes):
            raise ValueError("binary")
        return self._body


def mk_adapter(transport):
    settings = {"name": "EC-DSPS-TEST", "provider": "SCTS", "environment": "UAT",
                "base_url": "https://api-econtract.scts.com.vn",
                "base_url_allowlist": "api-econtract.scts.com.vn",
                "site": "eCentric", "username": "u@x",
                "token_expires_at": datetime(2027, 8, 22),   # cached token valid -> no login call
                "request_timeout": 30, "verify_tls": 1}
    return SctsAdapter(settings, transport=transport, sleeper=lambda s: None)


CALLS = []


class TestEcontractAdapter(unittest.TestCase):
    def setUp(self):
        del CALLS[:]

    # ---------------- create_document -> POST /api/Document/Submit ----------------
    DEFS = json.dumps([
        {"signatureId": "11CD2FCE-294C-49CA-BB24-EC724E3E65AD", "title": "Người trình",
         "role": "thamgia", "signatureType": "position", "keyword": "", "margin": 0.0,
         "canBeSigned": True, "added": 0},
        {"signatureId": "58145BD5-5D4C-4F6D-8E26-E160152C6F57", "title": "CEO",
         "role": "chinh", "signatureType": "position", "keyword": "", "margin": 0.0,
         "canBeSigned": True, "added": 0}])

    def test_create_document_new_contract(self):
        def transport(method, url, headers=None, json_body=None, **kw):
            CALLS.append((method, url, json_body))
            if url.endswith("/api/AddDocument/ConvertPdfFile"):
                return Resp(200, {"success": True, "data": {"originContentBase64": "",
                                  "contentBase64": "x", "jsonData": self.DEFS, "total": 2}})
            return Resp(200, {"success": True, "message": "Khởi tạo chứng từ thành công.",
                              "data": "7a90f618-5f90-4d8b-9f6a-a7a43364f596", "errors": None})
        a = mk_adapter(transport)
        ctx = {"doc_code": "EC-PAYR-2026-00022", "title": "UAT VOID de nghi thanh toan",
               "amount": 1000000, "deadline": "2026-09-01",
               "workflow_definition_id": "2580ACA5-620C-4107-A034-52873AD8FA10",
               "document_type_id": "1A34C80A-EC97-46C9-B210-BE0FD73C9433",
               "company_id": "ECENTRIC", "department_id": "cntt",
               "document_template_id": "",
               "files": [{"order": 0, "file_dsf": "DSF1", "name": "receipt.pdf",
                          "content": b"%PDF-1.4 test", "can_be_signed": True,
                          "is_supporting_document": False, "share_with_partner": False}],
               "placements": [{"signature_file": "DSF1", "page_index": 1,
                               "x": 100.5, "y": 200.25, "width": 120, "height": 40,
                               "level_no": 0, "signature_type": "mock",
                               "page_height": 792.0,
                               "scts_role_title": "Người trình"}]}
        out = a.create_document(ctx)
        self.assertTrue(CALLS[0][1].endswith("/api/AddDocument/ConvertPdfFile"))  # area lookup first
        m, url, body = CALLS[1]
        self.assertEqual(m, "POST")
        self.assertTrue(url.endswith("/api/AddDocument"), url)   # live route (docs Submit 405s)
        self.assertEqual(body["docCode"], "EC-PAYR-2026-00022")
        self.assertEqual(body["workflowDefinitionId"], ctx["workflow_definition_id"])
        self.assertEqual(body["companyId"], "ECENTRIC")
        self.assertEqual(body["deadlineDate"], "2026-09-01")
        self.assertEqual(body["ExternalHandlers"], [])
        d = body["Documents"][0]
        self.assertEqual(d["FileName"], "receipt.pdf")
        self.assertEqual(d["file_kind"], 1)
        self.assertTrue(d["CanBeSigned"]); self.assertFalse(d["uploadBct"])
        self.assertEqual(d["PdfBase64"], d["OriginalBase64"])
        self.assertEqual(base64.b64decode(d["PdfBase64"]), b"%PDF-1.4 test")
        sig = d["Signatures"][0]                                            # nested PER-DOCUMENT
        self.assertEqual(sig["signatureId"], "11CD2FCE-294C-49CA-BB24-EC724E3E65AD")  # template AREA id
        self.assertEqual(sig["title"], "Người trình"); self.assertEqual(sig["role"], "thamgia")
        self.assertEqual(sig["signatureType"], "position")
        self.assertEqual(sig["pageIndex"], 1)
        # Hai buoc, khong mot:
        #   1. lat truc doc: top-left y=200.25 h=40 tren trang 792pt -> PDF bottom-left 551.75
        #   2. doi don vi: SCTS doc con so minh gui nhu PIXEL 96 DPI roi nhan 0.75 (do dac
        #      02/09 tren tai lieu that). Nen phai gui truoc cai da bu:
        #         x = (100.5  - 19.95) / 0.75 = 107.40
        #         y = (551.75 - 47.74) / 0.75 = 672.01
        #         w = 120 / 0.75 = 160      h = 40 / 0.75 = 53
        #   Con so cuoi cung o day CO Y viet thanh so, khong tinh lai bang cong thuc: mot
        #   test lap lai cong thuc cua ma nguon thi no tu tra loi lay minh, doi cong thuc sai
        #   kieu gi cung xanh. Xem test_scts_coordinate_calibration cho phep do goc.
        self.assertEqual((sig["x"], sig["y"]), (107.4, 672.01))
        self.assertEqual((sig["Llx"], sig["Lly"]), (107.4, 672.01))
        self.assertEqual((sig["Width"], sig["Height"]), (160, 53))
        self.assertTrue(sig["isPlaced"]); self.assertEqual(sig["added"], 1)
        # response: data la STRING DocumentId
        self.assertEqual(out["document_id"], "7a90f618-5f90-4d8b-9f6a-a7a43364f596")

    def test_supporting_file_is_kind_2_without_signatures(self):
        def transport(method, url, headers=None, json_body=None, **kw):
            CALLS.append((method, url, json_body))
            return Resp(200, {"success": True, "data": "abc-123"})
        a = mk_adapter(transport)
        ctx = {"doc_code": "X", "title": "t",
               "workflow_definition_id": "w", "document_type_id": "d",
               "company_id": "c", "department_id": "p",
               "files": [{"order": 0, "file_dsf": "D2", "name": "bienban.pdf",
                          "content": b"%PDF", "can_be_signed": False,
                          "is_supporting_document": True, "share_with_partner": False}],
               "placements": []}
        a.create_document(ctx)
        self.assertFalse(any(u.endswith("ConvertPdfFile") for _m, u, _b in CALLS))  # no placements -> no lookup
        d = CALLS[-1][2]["Documents"][0]
        self.assertEqual(d["file_kind"], 2)
        self.assertEqual(d["Signatures"], [])


    def test_unmatched_title_fails_closed(self):
        def transport(method, url, headers=None, json_body=None, **kw):
            CALLS.append((method, url, json_body))
            if url.endswith("/api/AddDocument/ConvertPdfFile"):
                return Resp(200, {"success": True, "data": {"jsonData": self.DEFS, "total": 2}})
            return Resp(200, {"success": True, "data": "should-not-reach"})
        a = mk_adapter(transport)
        ctx = {"doc_code": "X", "title": "t", "workflow_definition_id": "w",
               "document_type_id": "d", "company_id": "c", "department_id": "p",
               "files": [{"order": 0, "file_dsf": "D1", "name": "a.pdf", "content": b"%PDF",
                          "can_be_signed": True, "is_supporting_document": False,
                          "share_with_partner": False}],
               "placements": [{"signature_file": "D1", "page_index": 1, "x": 1, "y": 2,
                               "width": 10, "height": 10, "scts_role_title": "Chức danh lạ"}]}
        from ecentric_workspace.platform.esign.providers.base import ProviderError as PE
        with self.assertRaises(PE) as e:
            a.create_document(ctx)
        self.assertEqual(e.exception.code, "scts_signature_area_unmatched")
        self.assertFalse(any(u.endswith("/api/AddDocument") for _m, u, _b in CALLS))  # no create sent

    # ---------------- GetSignatures normalize (contract moi khong co active flag) ----------------
    def test_signature_without_flags_is_active(self):
        sample = {"id": "638649a4-3920-4775-93bb-4575a08b0b7d",
                  "signerId": "73f72e15-4f56-4bde-84e9-68edd9918d7c",
                  "code": "KTG", "name": "Ký tham gia", "type": "ky-tham-gia",
                  "hsmCertId": "h", "companyId": "ECENTRIC",
                  "companyName": "CÔNG TY CỔ PHẦN ECENTRIC"}
        n = SctsAdapter._norm_signature(sample)
        self.assertTrue(n["active"])                       # presence in list = usable
        self.assertEqual(n["id"], sample["id"]); self.assertEqual(n["signerId"], sample["signerId"])

    def test_explicit_negative_still_fails_closed(self):
        self.assertFalse(SctsAdapter._resolve_active({"isActive": False}))
        self.assertFalse(SctsAdapter._resolve_active({"active": "0"}))
        self.assertFalse(SctsAdapter._resolve_active({"status": "revoked"}))
        self.assertTrue(SctsAdapter._resolve_active({"status": "active"}))

    # ---------------- poll normalize (statusName + signers tieng Viet, boc trong data) ----------------
    def test_poll_normalizes_vietnamese_detail(self):
        detail = {"success": True, "message": "OK",
                  "data": {"id": "c1d2b32f", "code": "0123",
                           "statusName": "Hoàn thành",
                           "files": [{"name": "hopdong.pdf", "type": "chinh"}],
                           "signers": [
                               {"user": "", "email": "hoan.tran@ecentric.vn", "roleText": "Ký chính",
                                "status": "Đã ký", "time": "2026-08-22 13:00", "isExternal": False},
                               {"user": "LAM NGUYEN VAN", "roleText": "Duyệt",
                                "status": "Chưa ký", "time": "Chưa có", "isExternal": False}]}}
        def transport(method, url, headers=None, json_body=None, **kw):
            return Resp(200, detail)
        a = mk_adapter(transport)
        st = a.poll_status("c1d2b32f")
        self.assertEqual(st.status, "completed")           # "Hoàn thành" -> completed
        self.assertEqual(st.signers[0]["status"], "signed")
        self.assertEqual(st.signers[0]["email"], "hoan.tran@ecentric.vn")
        self.assertEqual(st.signers[0]["signed_at"], "2026-08-22 13:00")
        self.assertEqual(st.signers[1]["status"], "pending")
        self.assertIsNone(st.signers[1]["signed_at"])      # "Chưa có" -> None

    def test_poll_processing_status(self):
        detail = {"success": True, "data": {"id": "x", "statusName": "Đang xử lý",
                                            "signers": [], "files": []}}
        a = mk_adapter(lambda *a2, **k: Resp(200, detail))
        self.assertEqual(a.poll_status("x").status, "processing")


    def test_verify_signed_by_email_when_no_userids(self):
        """eContract detail carries NO signer userIds - verification must succeed by the
        bound ERP user's email (observed live 2026-08-23: signer signed but verifier said
        expected_signer_absent)."""
        from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter
        detail = {"success": True, "data": {"id": "DOC-9",
                  "files": [{"id": "f1", "name": "a.pdf"}],
                  "signers": [
                      {"role": "chinh", "user": "", "email": "", "status": "Chưa ký", "time": "Chưa có"},
                      {"role": "thamgia", "user": "", "email": "hoan.tran@ecentric.vn",
                       "status": "Đã ký", "date": "23/08/2026", "time": "01:22"}]}}
        a = mk_adapter(lambda *a2, **k: Resp(200, detail))
        st = a.poll_status("DOC-9")
        vr = SignatureProviderAdapter.verify_signed_result(
            st, {"document_id": "DOC-9", "user_id": "73f72e15-nope",
                 "email": "hoan.tran@ecentric.vn", "file_count": 1})
        self.assertTrue(vr.ok, vr.reason)
        # sai email -> van fail-closed
        vr2 = SignatureProviderAdapter.verify_signed_result(
            st, {"document_id": "DOC-9", "user_id": "x", "email": "ai.do@ecentric.vn"})
        self.assertFalse(vr2.ok)

    # ---------------- signed PDF: data.pdfBase64 (contract da confirm) ----------------
    def test_get_pdf_nested_data_and_param_casing(self):
        pdf = b"%PDF-1.7 signed"
        def transport(method, url, headers=None, json_body=None, **kw):
            CALLS.append((method, url))
            return Resp(200, {"success": True,
                              "data": {"id": "f1", "fileName": "TEST.pdf", "fileType": "pdf",
                                       "pdfBase64": base64.b64encode(pdf).decode()}})
        c = SctsClient("https://api-econtract.scts.com.vn", transport=transport,
                       sleeper=lambda s: None)
        out = c.get_pdf("DOC1", "FILE1", "tok")
        self.assertEqual(out, pdf)
        self.assertIn("DocumentId=DOC1", CALLS[0][1])
        self.assertIn("DocumentFileId=FILE1", CALLS[0][1])

    # ---------------- cac contract GIU NGUYEN: login / GetSignatures / bulk-process ----------------
    def test_unchanged_routes(self):
        def transport(method, url, headers=None, json_body=None, **kw):
            CALLS.append((method, url, json_body))
            if url.endswith("/api/Auth/login"):
                return Resp(200, {"success": True,
                                  "data": {"userId": "u1", "token": "T", "expiresInMinutes": 525599}})
            if "/api/SignerSignature/GetSignatures/" in url:
                return Resp(200, {"success": True, "data": []})
            if url.endswith("/api/Workflow/bulk-process"):
                return Resp(200, {"success": True,
                                  "data": {"processed": 1, "failed": 0, "results": [
                                      {"instanceId": "i1", "status": "success"}]}})
            return Resp(404, {})
        c = SctsClient("https://api-econtract.scts.com.vn", transport=transport,
                       sleeper=lambda s: None)
        c.login("eCentric", "u", "p")
        c.get_signatures("uid-1", "tok")
        c.bulk_process(["i1"], "uid-1", "sig-1", "approve", "tok")
        login_body = CALLS[0][2]
        self.assertEqual(set(login_body.keys()) & {"Site", "Username", "Password"},
                         {"Site", "Username", "Password"})
        bulk_body = CALLS[2][2]
        self.assertEqual(bulk_body.get("transitionType"), "approve")
        self.assertIn("SignerSignatureId", bulk_body)
        self.assertEqual(bulk_body.get("instanceIds"), ["i1"])


if __name__ == "__main__":
    r = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if r.result.wasSuccessful() else 1)
