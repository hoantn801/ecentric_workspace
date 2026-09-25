# -*- coding: utf-8 -*-
"""Bo test cho cong LLM cua duong cham diem + phan boc `fetch_pdf_bytes`.

    python3 ecentric_workspace/weekly_report/tests/test_scoring_llm.py

Nap module bang exec(compile(...)) voi `frappe` gia -- KHONG import thuong, vi
__pycache__ co the vo hieu hoa dot bien (test doc .pyc cu van xanh sau khi da
sua nguon).

Hai dieu QUAN TRONG NHAT phai chung minh:
  1. `upload_from_sp_url` KHONG doi hanh vi sau khi boc `fetch_pdf_bytes` ra --
     no dang phuc vu duong cham diem that.
  2. Duong Kie KHONG BAO GIO gui THIEU tep. Thieu tep thi model van cham diem,
     cham tren du lieu khong day du -- kieu sai kho thay nhat, va no vao KPI.
"""
import io
import json
import os
import sys
import types
import unittest

REPO = os.environ.get("REPO", ".")


def load(path, extra=None):
    frappe = types.ModuleType("frappe")
    state = {"logs": [], "settings": {}}

    class _DB(object):
        def get_single_value(self, dt, f):
            return state["settings"].get(f, "")
    frappe.db = _DB()
    frappe.log_error = lambda **kw: state["logs"].append(kw)
    frappe.local = types.SimpleNamespace()
    frappe._ = lambda x: x

    def _wl(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f
    frappe.whitelist = _wl
    frappe.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "x"))
    utils = types.ModuleType("frappe.utils")
    utils.add_days = lambda d, n: d
    utils.nowdate = lambda: "2026-09-25"
    utils.get_datetime = lambda x=None: x
    utils.now_datetime = lambda: None
    utils.cint = lambda x, d=0: int(x or d)
    utils.cstr = lambda x: "" if x is None else str(x)
    utils.flt = lambda x, d=0: float(x or 0)
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: state["settings"].get(a[2] if len(a) > 2 else "", "")
    utils.password = pw
    frappe.utils = utils
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.utils.password"] = pw

    mod = types.ModuleType("m_" + os.path.basename(path).replace(".", "_"))
    mod.__dict__["__file__"] = path
    if extra:
        mod.__dict__.update(extra)
    exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
    return mod, state


G, GSTATE = load(os.path.join(REPO, "ecentric_workspace/gemini_api.py"))

# PHAI >= 100 byte: fetch_pdf_bytes tu choi tep qua nho (chong truong hop Graph
# tra ve mot trang loi ti hon thay vi PDF). Fixture 21 byte lam ca bo test do
# vi CHINH LUAT DO -- code dung, fixture sai.
PDF = b"%PDF-1.4\n" + b"noi dung gia " * 12


class FakeResp(object):
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status
        self.text = ""
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP %d" % self.status_code)
    def json(self):
        return {}


class TestFetchPdfBytes(unittest.TestCase):
    """Phan boc ra: phai giu nguyen moi cong kiem cua ban cu."""

    def setUp(self):
        self.calls = []
        G.requests = types.SimpleNamespace(
            get=lambda url, **kw: (self.calls.append(url), self._resp)[1],
            post=lambda *a, **k: FakeResp())
        self._resp = FakeResp(PDF)

    def test_pptx_duoc_yeu_cau_chuyen_sang_pdf(self):
        G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pptx", "TK", "")
        self.assertTrue(any("format=pdf" in u for u in self.calls),
                        "Office phai kem ?format=pdf -- day la buoc khien Gemini/Kie doc duoc")

    def test_pdf_san_thi_KHONG_them_format_pdf(self):
        G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pdf", "TK", "")
        self.assertFalse(any("format=pdf" in u for u in self.calls))

    def test_doi_duoi_thanh_pdf_khi_da_chuyen(self):
        r = G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pptx", "TK", "")
        self.assertTrue(r["ok"])
        self.assertTrue(r["display_name"].endswith(".pdf"))
        self.assertEqual(r["converted_from"], "pptx")

    def test_khong_phai_PDF_thi_TU_CHOI(self):
        self._resp = FakeResp(b"<html>loi</html>" * 20)
        r = G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pptx", "TK", "")
        self.assertFalse(r["ok"])
        self.assertIn("Not a valid PDF", r["error"])

    def test_tep_qua_nho_thi_TU_CHOI(self):
        self._resp = FakeResp(b"%PDF")
        r = G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pdf", "TK", "")
        self.assertFalse(r["ok"])
        self.assertIn("too small", r["error"])

    def test_token_KHONG_lot_vao_thong_bao_loi(self):
        def boom(url, **kw):
            raise Exception("failed with Bearer SIEU-BI-MAT-123")
        G.requests = types.SimpleNamespace(get=boom, post=lambda *a, **k: FakeResp())
        r = G.fetch_pdf_bytes("https://x/sites/operation/Shared Documents/a/deck.pdf",
                              "SIEU-BI-MAT-123", "")
        self.assertFalse(r["ok"])
        self.assertNotIn("SIEU-BI-MAT-123", r["error"])


class TestUploadKhongDoiHanhVi(unittest.TestCase):
    """Boc ham ra KHONG duoc lam doi duong cu (dang phuc vu cham diem that)."""

    def setUp(self):
        G.requests = types.SimpleNamespace(get=lambda url, **kw: FakeResp(PDF),
                                           post=lambda *a, **k: FakeResp())
        self.uploaded = {}
        def fake_upload(data, name, mime, key, **kw):
            self.uploaded.update({"data": data, "name": name, "mime": mime, "key": key})
            return {"success": True, "uri": "files/abc", "name": name,
                    "display_name": name, "mime_type": mime, "active": True,
                    "expires_at": "2026-01-01"}
        G.upload_bytes = fake_upload

    def test_van_tra_ve_uri_va_size(self):
        r = G.upload_from_sp_url("https://x/sites/operation/Shared Documents/a/deck.pptx",
                                 "TK", "KEY", dept_clean="")
        self.assertTrue(r["success"], r.get("error"))
        self.assertEqual(r["uri"], "files/abc")
        self.assertEqual(r["size_bytes"], len(PDF))
        self.assertEqual(r["converted_from"], "pptx")

    def test_van_day_len_PDF_da_chuyen_chu_khong_phai_pptx(self):
        G.upload_from_sp_url("https://x/sites/operation/Shared Documents/a/deck.pptx",
                             "TK", "KEY", dept_clean="")
        self.assertEqual(self.uploaded["mime"], "application/pdf")
        self.assertTrue(self.uploaded["name"].endswith(".pdf"))
        self.assertEqual(self.uploaded["data"], PDF)

    def test_tai_hong_thi_KHONG_day_len_Google(self):
        G.requests = types.SimpleNamespace(
            get=lambda url, **kw: FakeResp(b"<html>", 200), post=lambda *a, **k: FakeResp())
        r = G.upload_from_sp_url("https://x/sites/operation/Shared Documents/a/deck.pptx",
                                 "TK", "KEY", dept_clean="")
        self.assertFalse(r["success"])
        self.assertEqual(self.uploaded, {}, "tai hong ma van goi upload = dot tien va gui rac")


# scoring_llm.py co `from ecentric_workspace import gemini_api` o tang module.
# Cam mot goi gia mang san G vao sys.modules de exec() khong phai co ca package.
_pkg = types.ModuleType("ecentric_workspace")
_pkg.__path__ = []
_pkg.gemini_api = G
sys.modules["ecentric_workspace"] = _pkg
sys.modules["ecentric_workspace.gemini_api"] = G

# `_extract_rel_path` uy quyen sang weekly_report.sharepoint LUC CHAY. Dung ban
# THAT chu khong gia: neu gia thi bo test se khong con phat hien duoc truong hop
# URL dang "org share link" ma sharepoint.py moi xu ly duoc -- dung cai da lam
# hong ca hang doi cham diem hom 15/09.
_wr = types.ModuleType("ecentric_workspace.weekly_report")
_wr.__path__ = []
sys.modules["ecentric_workspace.weekly_report"] = _wr
_SP, _ = load(os.path.join(REPO, "ecentric_workspace/weekly_report/sharepoint.py"))
sys.modules["ecentric_workspace.weekly_report.sharepoint"] = _SP
_wr.sharepoint = _SP

S, SSTATE = load(os.path.join(REPO, "ecentric_workspace/weekly_report/scoring_llm.py"),
                 extra={"gemini_api": G})


class TestCongChamDiem(unittest.TestCase):
    """CANH BAO: `S.gemini_api` CHINH LA module G, khong phai ban sao. Gan de
    G.fetch_pdf_bytes trong mot test la doi HAM THAT cua module, va moi test
    chay sau se nhan stub -- bo test tu dau doc nhau. Da dinh 25/09: chay rieng
    thi xanh, chay ca bo thi 6 do. Vi vay setUp luu lai va tearDown tra ve."""

    def setUp(self):
        GSTATE["settings"].clear()
        self._goc = {"fetch_pdf_bytes": G.fetch_pdf_bytes,
                     "generate_json": G.generate_json}
        self._sp_goc = _wr.sharepoint
        self.sent = {}
        def fake_gen(prompt, response_schema, system_instruction=None, files=None, **kw):
            self.sent["files"] = files
            self.sent["prompt"] = prompt
            return {"ok": True, "data": {"diem": 8}, "error": None,
                    "provider": G.provider(), "fell_back": False,
                    "model": "m", "latency_ms": 1}
        G.generate_json = fake_gen
        S.gemini_api = G

    def tearDown(self):
        for k, v in self._goc.items():
            setattr(G, k, v)
        _wr.sharepoint = self._sp_goc
        sys.modules["ecentric_workspace.weekly_report.sharepoint"] = self._sp_goc

    def _dat_sharepoint_gia(self, token_fn):
        """`from ecentric_workspace.weekly_report import sharepoint` lay THUOC
        TINH cua goi truoc khi ngo toi sys.modules -- chi cam vao sys.modules la
        bi bo qua, van dung module that (va get_app_token that se goi
        frappe.get_doc). Phai dat CA HAI."""
        sp = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
        sp.get_app_token = token_fn
        sys.modules["ecentric_workspace.weekly_report.sharepoint"] = sp
        _wr.sharepoint = sp
        return sp

    def test_provider_google_thi_dung_URI_khong_tai_bytes(self):
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "files/x", "mime_type": "application/pdf"}]),
                              slide_deck="https://x/a.pptx")
        self.assertTrue(out["ok"])
        self.assertEqual(self.sent["files"][0]["uri"], "files/x")
        self.assertNotIn("data", self.sent["files"][0], "Google khong can bytes")

    def test_kie_tai_bytes_va_GIU_uri_de_du_phong(self):
        GSTATE["settings"]["ec_llm_provider"] = "kie"
        S.gemini_api.fetch_pdf_bytes = lambda u, t, d: {
            "ok": True, "data": PDF, "display_name": "a.pdf", "size_bytes": len(PDF)}
        self._dat_sharepoint_gia(lambda: "TK")
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "files/x", "mime_type": "application/pdf"}]),
                              slide_deck="https://x/a.pptx")
        self.assertTrue(out["ok"])
        f0 = self.sent["files"][0]
        self.assertEqual(f0["data"], PDF, "Kie phai nhan bytes")
        self.assertEqual(f0["uri"], "files/x", "van giu URI de con roi ve Google duoc")

    def test_tai_bytes_HONG_thi_di_Google_chu_KHONG_gui_thieu_tep(self):
        GSTATE["settings"]["ec_llm_provider"] = "kie"
        S.gemini_api.fetch_pdf_bytes = lambda u, t, d: {"ok": False, "error": "Graph 500"}
        self._dat_sharepoint_gia(lambda: "TK")
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "files/x", "mime_type": "application/pdf"}]),
                              slide_deck="https://x/a.pptx\nhttps://x/b.pptx")
        self.assertEqual(self.sent["files"][0]["uri"], "files/x")
        self.assertNotIn("data", self.sent["files"][0])
        self.assertIn("Graph 500", out.get("kie_skipped", ""))

    def test_MOT_tep_hong_thi_BO_CA_LUOT_khong_gui_mot_nua(self):
        GSTATE["settings"]["ec_llm_provider"] = "kie"
        seq = [{"ok": True, "data": PDF, "display_name": "a.pdf", "size_bytes": len(PDF)},
               {"ok": False, "error": "tep 2 hong"}]
        S.gemini_api.fetch_pdf_bytes = lambda u, t, d: seq.pop(0)
        self._dat_sharepoint_gia(lambda: "TK")
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "u1"}, {"uri": "u2"}]),
                              slide_deck="https://x/a.pptx\nhttps://x/b.pptx")
        self.assertEqual(len(self.sent["files"]), 2, "phai giu DU 2 URI cua Google")
        self.assertNotIn("data", self.sent["files"][0], "khong duoc gui 1 bytes + 1 thieu")

    def test_vuot_tran_inline_thi_di_Google(self):
        GSTATE["settings"]["ec_llm_provider"] = "kie"
        big = b"%PDF" + b"x" * (S.MAX_INLINE_TOTAL + 10)
        S.gemini_api.fetch_pdf_bytes = lambda u, t, d: {
            "ok": True, "data": big, "display_name": "a.pdf", "size_bytes": len(big)}
        self._dat_sharepoint_gia(lambda: "TK")
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "files/x"}]),
                              slide_deck="https://x/a.pptx")
        self.assertIn("vuot tran", out.get("kie_skipped", ""))
        self.assertNotIn("data", self.sent["files"][0])

    def test_khong_lay_duoc_token_thi_di_Google(self):
        GSTATE["settings"]["ec_llm_provider"] = "kie"
        def boom():
            raise Exception("SSO hong")
        self._dat_sharepoint_gia(boom)
        out = S.score_via_llm("P", {"type": "object"},
                              file_uris=json.dumps([{"uri": "files/x"}]),
                              slide_deck="https://x/a.pptx")
        self.assertIn("Graph token", out.get("kie_skipped", ""))
        self.assertTrue(out["ok"])

    def test_schema_dang_chuoi_van_parse_duoc(self):
        out = S.score_via_llm("P", json.dumps({"type": "object"}), file_uris="[]")
        self.assertTrue(out["ok"])

    def test_khong_co_slide_thi_van_cham_duoc(self):
        out = S.score_via_llm("P", {"type": "object"}, file_uris="[]", slide_deck="")
        self.assertTrue(out["ok"])
        self.assertEqual(out["files_sent"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
