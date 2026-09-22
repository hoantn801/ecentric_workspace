# -*- coding: utf-8 -*-
"""Bo test cho lop nha cung cap LLM (Kie chinh, Google du phong).

    python3 ecentric_workspace/approval_center/tests/standalone/test_llm_provider.py

CHAY DUOC NGOAI FRAPPE: nap gemini_api.py bang exec(compile(...)) voi mot
`frappe` gia. Khong dung import thuong vi __pycache__ co the vo hieu hoa dot
bien - bai hoc 2026: test doc file .pyc cu van xanh sau khi da sua nguon.

MOI THAN SSE TRONG FILE NAY LA THAN THAT, chep tu ket qua chay
`C:\\dev\\probe_kie_gemini.ps1` ngay 22/09/2026 tren may PO. Khong tu bia hinh
dang - hinh dang tu bia la cach test xanh ma production van hong.
"""
import io
import json
import os
import sys
import types
import unittest

REPO = os.environ.get("REPO", ".")
SRC = os.path.join(REPO, "ecentric_workspace", "gemini_api.py")


def load_module():
    """Nap gemini_api.py voi `frappe` gia. Tra ve (module, settings_dict)."""
    settings = {}

    frappe = types.ModuleType("frappe")

    class _DB(object):
        def get_single_value(self, doctype, field):
            return settings.get(field, "")

    frappe.db = _DB()
    # gemini_api.py co @frappe.whitelist() o tang module -> decorator phai ton tai
    # va phai tra lai chinh ham, neu khong cac ham do bien mat khoi module.
    def _whitelist(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f
    frappe.whitelist = _whitelist
    frappe.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    frappe.log_error = lambda **kw: settings.setdefault("_logs", []).append(kw)
    frappe.local = types.SimpleNamespace()
    frappe._ = lambda x: x

    utils = types.ModuleType("frappe.utils")
    password = types.ModuleType("frappe.utils.password")
    password.get_decrypted_password = lambda *a, **k: settings.get(a[2] if len(a) > 2 else "", "")
    utils.password = password
    frappe.utils = utils

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.utils.password"] = password

    mod = types.ModuleType("gemini_api_under_test")
    mod.__dict__["__file__"] = SRC
    text = io.open(SRC, encoding="utf-8").read()
    exec(compile(text, SRC, "exec"), mod.__dict__)
    return mod, settings


G, SETTINGS = load_module()


# ── Than SSE THAT tu lan chay 22/09 ──────────────────────────────────────────
# Van ban bi cat lam doi: chunk 1 dut giua chuoi JSON.
SSE_THAT = (
    'data: {"candidates": [{"content": {"role": "model", "parts": '
    '[{"text": "{\\"diem\\": 7, \\"ly_do\\": \\""}]}}]}\n'
    '\n'
    '\n'
    'data: {"candidates": [{"content": {"role": "model", "parts": '
    '[{"text": "Cham diem 7 theo yeu cau.\\"}"}]}}]}\n'
    '\n'
    '\n'
    'data: {"usageMetadata":{"thinkingTokenCount":225,"candidatesTokenCount":23,'
    '"totalTokenCount":306,"promptTokenCount":12},"credits_consumed":0.01}\n'
)
SSE_MOT_CHUNK = (
    'data: {"candidates": [{"content": {"role": "model", "parts": '
    '[{"text": "{\\"diem\\":7,\\"ly_do\\":\\"Trinh bay ro\\"}"}]}}]}\n'
)
THAN_LOI_500 = '{"code":500,"msg":"internal error, please try again later."}'
THAN_LOI_400 = '{"code":400,"msg":"unsupported file type: ...pptx"}'


class TestDocStream(unittest.TestCase):
    """Van ban bi cat qua nhieu chunk -- lay chunk dau la nhan JSON cut."""

    def test_noi_du_hai_chunk_thanh_json_hop_le(self):
        text = G.parse_sse_text(SSE_THAT)
        self.assertEqual(text, '{"diem": 7, "ly_do": "Cham diem 7 theo yeu cau."}')
        self.assertEqual(json.loads(text)["diem"], 7)

    def test_lay_mot_chunk_dau_la_JSON_CUT(self):
        """Ghim tien de: neu chi lay chunk dau thi KHONG parse duoc.
        Phep thu nay chung minh viec noi chunk la CAN THIET, khong phai thua."""
        dong_dau = SSE_THAT.splitlines()[0]
        chunk = json.loads(dong_dau[5:].strip())
        chi_chunk_dau = chunk["candidates"][0]["content"]["parts"][0]["text"]
        with self.assertRaises(ValueError):
            json.loads(chi_chunk_dau)

    def test_mot_chunk_van_chay(self):
        self.assertEqual(json.loads(G.parse_sse_text(SSE_MOT_CHUNK))["ly_do"],
                         "Trinh bay ro")

    def test_bo_qua_chunk_chi_co_usageMetadata(self):
        chi_usage = SSE_THAT.splitlines()[-1]
        self.assertEqual(G.parse_sse_text(chi_usage + "\n"), "")

    def test_than_rong_va_rac_khong_nem(self):
        self.assertEqual(G.parse_sse_text(""), "")
        self.assertEqual(G.parse_sse_text(None), "")
        self.assertEqual(G.parse_sse_text("data: {khong-phai-json\n"), "")

    def test_bo_qua_DONE(self):
        self.assertEqual(G.parse_sse_text(SSE_MOT_CHUNK + "data: [DONE]\n"),
                         '{"diem":7,"ly_do":"Trinh bay ro"}')


class TestNhanLoi(unittest.TestCase):
    """Kie bao loi bang HTTP 200 + code trong than -- raise_for_status() mu."""

    def test_code_500_trong_than_bi_bat(self):
        self.assertIn("500", G.kie_error(THAN_LOI_500))

    def test_code_400_trong_than_bi_bat(self):
        self.assertIn("400", G.kie_error(THAN_LOI_400))

    def test_than_SSE_hop_le_KHONG_bi_coi_la_loi(self):
        """SSE khong phai JSON nen json.loads that bai -- do la binh thuong."""
        self.assertEqual(G.kie_error(SSE_THAT), "")

    def test_than_rong_la_loi(self):
        self.assertTrue(G.kie_error(""))


class TestTepInline(unittest.TestCase):
    """Kie khong dung duoc URI cua Google -> phai co bytes, va co tran."""

    def test_khong_co_bytes_thi_tu_choi(self):
        parts, why = G.split_files_for_kie([{"uri": "files/abc", "mime_type": "application/pdf"}])
        self.assertEqual(parts, [])
        self.assertIn("URI", why)

    def test_co_bytes_thi_dung_inlineData(self):
        parts, why = G.split_files_for_kie(
            [{"data": b"xin chao", "mime_type": "application/pdf"}])
        self.assertEqual(why, "")
        self.assertEqual(parts[0]["inlineData"]["mimeType"], "application/pdf")
        import base64
        self.assertEqual(base64.b64decode(parts[0]["inlineData"]["data"]), b"xin chao")

    def test_vuot_tran_thi_tu_choi_CA_LAN_GOI(self):
        parts, why = G.split_files_for_kie(
            [{"data": b"x" * 2048, "mime_type": "application/pdf"}], max_bytes=1024)
        self.assertEqual(parts, [])
        self.assertIn("tran", why)

    def test_tong_nhieu_tep_moi_vuot_tran(self):
        files = [{"data": b"x" * 600, "mime_type": "application/pdf"},
                 {"data": b"y" * 600, "mime_type": "application/pdf"}]
        parts, why = G.split_files_for_kie(files, max_bytes=1000)
        self.assertEqual(parts, [], "tong 1200 > 1024 nhung tung tep deu duoi tran")

    def test_khong_co_tep_thi_khong_sao(self):
        self.assertEqual(G.split_files_for_kie(None), ([], ""))


class TestThanRequest(unittest.TestCase):
    """Than GIONG HET cho ca hai nha cung cap -- do tham do 22/09 xac nhan."""

    def test_giu_responseSchema_va_temperature_0(self):
        body = G.build_body("hoi", {"type": "OBJECT"}, None, None)
        gc = body["generationConfig"]
        self.assertEqual(gc["responseSchema"], {"type": "OBJECT"})
        self.assertEqual(gc["temperature"], 0)
        self.assertEqual(gc["responseMimeType"], "application/json")

    def test_tep_dat_TRUOC_van_ban(self):
        fp = [{"inlineData": {"mimeType": "application/pdf", "data": "AA"}}]
        parts = G.build_body("hoi", {}, None, fp)["contents"][0]["parts"]
        self.assertIn("inlineData", parts[0])
        self.assertEqual(parts[-1], {"text": "hoi"})

    def test_system_instruction_chi_co_khi_duoc_truyen(self):
        self.assertNotIn("systemInstruction", G.build_body("h", {}, None, None))
        self.assertIn("systemInstruction", G.build_body("h", {}, "luat", None))


class TestDinhTuyen(unittest.TestCase):
    """Mac dinh PHAI la Google; Kie hong -> tu roi ve Google."""

    def setUp(self):
        SETTINGS.clear()
        self.goi = []

    def test_mac_dinh_la_google(self):
        self.assertEqual(G.provider(), "google")

    def test_gia_tri_la_bat_ky_thi_van_la_google(self):
        SETTINGS["ec_llm_provider"] = "openai"
        self.assertEqual(G.provider(), "google")
        SETTINGS["ec_llm_provider"] = "KIE"
        self.assertEqual(G.provider(), "kie")

    def _vaKie(self, tra):
        def fake(body, timeout):
            self.goi.append("kie")
            return tra
        G._call_kie = fake

    def _vaGoogle(self, tra):
        def fake(body, model, timeout):
            self.goi.append("google")
            return tra
        G._call_google = fake

    def test_provider_google_thi_KHONG_goi_kie(self):
        self._vaKie(("", "khong duoc goi")); self._vaGoogle(('{"a":1}', ""))
        out = G.generate_json("h", {})
        self.assertEqual(self.goi, ["google"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["provider"], "google")
        self.assertFalse(out["fell_back"])

    def test_kie_chay_thi_KHONG_goi_google(self):
        SETTINGS["ec_llm_provider"] = "kie"
        SETTINGS["ec_kie_api_key"] = "k"
        self._vaKie(('{"a":1}', "")); self._vaGoogle(("", "khong duoc goi"))
        out = G.generate_json("h", {})
        self.assertEqual(self.goi, ["kie"])
        self.assertEqual(out["provider"], "kie")
        self.assertFalse(out["fell_back"])

    def test_kie_hong_thi_ROI_VE_google_trong_cung_lan_goi(self):
        SETTINGS["ec_llm_provider"] = "kie"
        SETTINGS["ec_kie_api_key"] = "k"
        self._vaKie(("", "Kie code=500")); self._vaGoogle(('{"a":1}', ""))
        out = G.generate_json("h", {})
        self.assertEqual(self.goi, ["kie", "google"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["provider"], "google")
        self.assertTrue(out["fell_back"], "phai danh dau da roi ve du phong")

    def test_ca_hai_hong_thi_giu_CA_HAI_ly_do(self):
        SETTINGS["ec_llm_provider"] = "kie"
        SETTINGS["ec_kie_api_key"] = "k"
        self._vaKie(("", "Kie code=500")); self._vaGoogle(("", "Google 400"))
        out = G.generate_json("h", {})
        self.assertFalse(out["ok"])
        self.assertIn("Kie code=500", out["error"])
        self.assertIn("Google 400", out["error"])

    def test_tep_khong_co_bytes_thi_di_thang_google_KHONG_goi_kie(self):
        SETTINGS["ec_llm_provider"] = "kie"
        SETTINGS["ec_kie_api_key"] = "k"
        self._vaKie(("", "khong duoc goi")); self._vaGoogle(('{"a":1}', ""))
        out = G.generate_json("h", {}, files=[{"uri": "files/x", "mime_type": "application/pdf"}])
        self.assertEqual(self.goi, ["google"], "thieu bytes thi khong duoc thu Kie")
        self.assertTrue(out["fell_back"])

    def test_google_nhan_fileData_uri_chu_khong_phai_inline(self):
        got = {}
        def fake(body, model, timeout):
            got["body"] = body
            return ('{"a":1}', "")
        G._call_google = fake
        G.generate_json("h", {}, files=[{"uri": "files/x", "mime_type": "application/pdf"}])
        p0 = got["body"]["contents"][0]["parts"][0]
        self.assertEqual(p0["fileData"]["fileUri"], "files/x")

    def test_JSON_hong_thi_bao_loi_chu_khong_tra_dict_rong(self):
        self._vaGoogle(("khong phai json", ""))
        out = G.generate_json("h", {})
        self.assertFalse(out["ok"])
        self.assertIsNone(out["data"])
        self.assertIn("khong doc duoc JSON", out["error"])

    def test_model_tra_ve_mang_thi_bao_loi(self):
        self._vaGoogle(("[1,2,3]", ""))
        out = G.generate_json("h", {})
        self.assertFalse(out["ok"])
        self.assertIn("can mot doi tuong JSON", out["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
