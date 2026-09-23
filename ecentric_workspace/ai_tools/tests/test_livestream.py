# Copyright (c) 2026, eCentric and contributors
"""Endpoint sinh script AI Livestream: Kie chinh, Google du phong, CO TRAN THOI GIAN.

    python3 ecentric_workspace/ai_tools/tests/test_livestream.py

Chay ngoai Frappe: nap livestream.py VA gemini_api.py THAT bang exec voi `frappe` + `requests`
gia (exec thay vi import de __pycache__ khong vo hieu hoa dot bien).

Moi luat co mau DAT va mau TRUOT. Phep dat nhat: `test_kie_json_cut_thi_roi_ve_google` -
do 23/09, 3/9 luot Kie bi cat JSON va Server Script cu tra thang BAD_JSON cho nguoi dung.
"""
import io
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
SRC_LS = os.path.join(APP, "ai_tools", "livestream.py")
SRC_LLM = os.path.join(APP, "gemini_api.py")

GOOD = {"parts": {"intro": "Chào anh chị.", "ksp": "Bông mềm.", "howto": "Thấm ướt.",
                  "cta": "Chốt đơn nha."}, "claims_used": []}


def sse(text, usage=None, finish="STOP"):
    """Than SSE kieu Kie: van ban CAT DOI qua hai chunk (hinh dang that do 22/09)."""
    half = len(text) // 2
    chunks = [text[:half], text[half:]]
    out = ""
    for i, piece in enumerate(chunks):
        cand = {"content": {"role": "model", "parts": [{"text": piece}]}}
        if i == len(chunks) - 1 and finish:
            cand["finishReason"] = finish
        out += "data: " + json.dumps({"candidates": [cand]}, ensure_ascii=False) + "\n\n"
    out += "data: " + json.dumps({"usageMetadata": usage or {"totalTokenCount": 9000}}) + "\n\n"
    return out


class FakeResp(object):
    def __init__(self, body=b"", status=200, obj=None):
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.status_code = status
        self._obj = obj
        # Giong requests: text/event-stream khong khai charset -> doan ISO-8859-1.
        self.encoding = "ISO-8859-1"

    @property
    def text(self):
        return self.content.decode(self.encoding, errors="replace")

    def json(self):
        return self._obj if self._obj is not None else json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP %s" % self.status_code)


def load(settings=None, roles=("EC AI Content",), replies=None):
    """-> (ls_module, state). `replies`: list cac ham (url, kw) -> FakeResp | raise."""
    st = {"settings": dict({"ec_ail_prompt": "PROMPT", "ec_llm_provider": "kie",
                            "ec_kie_api_key": "KIEKEY", "ec_gemini_api_key": "GKEY"},
                           **(settings or {})),
          "calls": [], "logs": [], "replies": list(replies or [])}

    fk = types.ModuleType("frappe")

    class _DB(object):
        def get_single_value(self, dt, field):
            return st["settings"].get(field, "")
    fk.db = _DB()
    fk.session = types.SimpleNamespace(user="content@ecentric.vn")
    fk.get_roles = lambda user=None: list(roles)
    fk.log_error = lambda *a, **k: st["logs"].append(k.get("title") or (a[0] if a else ""))
    fk.local = types.SimpleNamespace()
    fk._ = lambda x: x

    def _whitelist(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f
    fk.whitelist = _whitelist
    fk.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    utils = types.ModuleType("frappe.utils")
    utils.now = lambda: "2026-09-23 13:00:00.123456"
    password = types.ModuleType("frappe.utils.password")
    password.get_decrypted_password = lambda dt, name, field, **k: st["settings"].get(field, "")
    utils.password = password
    fk.utils = utils

    rq = types.ModuleType("requests")

    def _post(url, **kw):
        st["calls"].append((url, kw))
        if not st["replies"]:
            raise AssertionError("goi HTTP ngoai du kien: %s" % url)
        return st["replies"].pop(0)(url, kw)
    rq.post = _post
    rq.get = _post

    pkg = types.ModuleType("ecentric_workspace")
    pkg.__path__ = []
    sys.modules.update({"frappe": fk, "frappe.utils": utils, "frappe.utils.password": password,
                        "requests": rq, "ecentric_workspace": pkg})
    llm = types.ModuleType("ecentric_workspace.gemini_api")
    with io.open(SRC_LLM, encoding="utf-8") as fh:
        exec(compile(fh.read(), SRC_LLM, "exec"), llm.__dict__)
    sys.modules["ecentric_workspace.gemini_api"] = llm
    pkg.gemini_api = llm
    ls = types.ModuleType("livestream_under_test")
    with io.open(SRC_LS, encoding="utf-8") as fh:
        exec(compile(fh.read(), SRC_LS, "exec"), ls.__dict__)
    return ls, st


def kie_ok(text=None):
    return lambda url, kw: FakeResp(sse(text or json.dumps(GOOD, ensure_ascii=False)))


def google_ok(obj=None):
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps(obj or GOOD, ensure_ascii=False)}]},
                            "finishReason": "STOP"}], "usageMetadata": {"totalTokenCount": 6000}}
    return lambda url, kw: FakeResp(json.dumps(body), obj=body)


def boom(exc):
    def _r(url, kw):
        raise exc
    return _r


REQ = json.dumps({"task": "DE BAI", "preset": "full"})


class TestDuongChinh(unittest.TestCase):
    def test_kie_ok_thi_khong_goi_google(self):
        ls, st = load(replies=[kie_ok()])
        r = ls.generate(REQ)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["provider"], r["model"], r["fell_back"]), ("kie", "gemini-3-8-flash", False))
        self.assertEqual(r["result"], GOOD)
        self.assertEqual(r["tokens"], 9000)
        self.assertEqual(len(st["calls"]), 1)
        self.assertIn("api.kie.ai", st["calls"][0][0])

    def test_tieng_viet_khong_vo_khi_sse_khong_khai_charset(self):
        ls, st = load(replies=[kie_ok()])
        r = ls.generate(REQ)
        self.assertEqual(r["result"]["parts"]["cta"], "Chốt đơn nha.")

    def test_cong_tac_google_thi_khong_cham_toi_kie(self):
        ls, st = load(settings={"ec_llm_provider": "google"}, replies=[google_ok()])
        r = ls.generate(REQ)
        self.assertEqual((r["provider"], r["model"], r["fell_back"]), ("google", "gemini-2.5-flash", False))
        self.assertEqual(len(st["calls"]), 1)
        self.assertIn("googleapis.com", st["calls"][0][0])


REQ_FB = json.dumps({"task": "DE BAI", "preset": "full", "allow_fallback": True})


class TestKhongTuRoiVeGoogle(unittest.TestCase):
    """Vinh chot 23/09: Kie hong thi BAO, nguoi dung tu chon 2.5. Khong goi Google lan nao."""
    def _stop(self, kie_reply):
        ls, st = load(replies=[kie_reply])
        r = ls.generate(REQ)
        self.assertFalse(r["ok"])
        self.assertEqual((r["error"], r["provider"]), ("KIE_LOI", "kie"))
        self.assertEqual(len(st["calls"]), 1)            # KHONG co luot Google
        self.assertNotIn("ec_llm_fallback_to_google", st["logs"])
        return r

    def test_kie_json_cut_thi_bao_chu_khong_goi_google(self):
        r = self._stop(kie_ok(json.dumps(GOOD, ensure_ascii=False)[:40]))
        self.assertIn("kie_json_hong", r["detail"])

    def test_kie_treo_thi_bao(self):
        self.assertIn("ReadTimeout", self._stop(boom(Exception("ReadTimeout")))["detail"])

    def test_nguoi_dung_chon_google_thi_khong_cham_kie(self):
        ls, st = load(replies=[google_ok()])
        r = ls.generate(json.dumps({"task": "DE BAI", "provider": "google"}))
        self.assertEqual((r["ok"], r["provider"], r["fell_back"]), (True, "google", False))
        self.assertIn("googleapis.com", st["calls"][0][0])

    def test_notes_cua_ai_di_nguyen_ve_trang(self):
        empty = {"parts": {"intro": "", "ksp": "", "howto": "", "cta": ""}, "claims_used": [],
                 "notes": "Chua du thong tin ve tam bong."}
        ls, st = load(replies=[kie_ok(json.dumps(empty))])
        r = ls.generate(REQ)
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["notes"], "Chua du thong tin ve tam bong.")
        self.assertEqual(len(st["calls"]), 1)


class TestDuPhong(unittest.TestCase):
    """Duong roi tu dong VAN con, nhung chi khi goi voi allow_fallback."""
    def _fell_back(self, kie_reply):
        ls, st = load(replies=[kie_reply, google_ok()])
        r = ls.generate(REQ_FB)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["provider"], r["fell_back"]), ("google", True))
        self.assertIn("ec_llm_fallback_to_google", st["logs"])
        return r, st

    def test_kie_json_cut_thi_roi_ve_google(self):
        cut = json.dumps(GOOD, ensure_ascii=False)[:40]
        self._fell_back(kie_ok(cut))

    def test_kie_bao_loi_bang_http_200_code_500(self):
        self._fell_back(lambda url, kw: FakeResp('{"code":500,"msg":"Server exception"}'))

    def test_kie_treo_qua_tran_thi_roi_ve_google(self):
        self._fell_back(boom(Exception("ReadTimeout")))

    def test_ca_hai_hong_thi_giu_ca_hai_ly_do(self):
        ls, st = load(replies=[boom(Exception("ReadTimeout")), boom(Exception("503"))])
        r = ls.generate(REQ_FB)
        self.assertFalse(r["ok"])
        self.assertIn("ReadTimeout", r["detail"])
        self.assertIn("503", r["detail"])


class TestTranThoiGian(unittest.TestCase):
    """Ly do DUY NHAT cua module nay: moi lan goi phai co tran, va tong tran nho hon 120s."""
    def test_moi_lan_goi_deu_co_timeout(self):
        ls, st = load(replies=[boom(Exception("ReadTimeout")), google_ok()])
        ls.generate(REQ_FB)
        self.assertEqual(len(st["calls"]), 2)
        for url, kw in st["calls"]:
            self.assertIn("timeout", kw, url)
            self.assertTrue(kw["timeout"], url)

    def test_tong_tran_nho_hon_gioi_han_worker(self):
        ls, _ = load()
        self.assertLess(sum(ls.KIE_TIMEOUT) + sum(ls.GOOGLE_TIMEOUT), 120)


class TestTranToken(unittest.TestCase):
    def test_kie_duoc_tran_rieng_lon_hon(self):
        ls, st = load(replies=[boom(Exception("x")), google_ok()])
        ls.generate(REQ_FB)
        kie_cfg = st["calls"][0][1]["json"]["generationConfig"]
        g_cfg = st["calls"][1][1]["json"]["generationConfig"]
        self.assertEqual(kie_cfg["maxOutputTokens"], 32000)
        self.assertEqual(g_cfg["maxOutputTokens"], 8000)
        # thinking BAT o ca hai - tat thinking tung lam so luat bi pha tang 4 -> 13
        self.assertEqual(kie_cfg["thinkingConfig"]["thinkingBudget"], 2048)


class TestCong(unittest.TestCase):
    def test_khong_co_role_thi_khong_goi_http(self):
        ls, st = load(roles=("Employee",))
        r = ls.generate(REQ)
        self.assertEqual(r["error"], "NO_ROLE")
        self.assertEqual(st["calls"], [])

    def test_system_manager_duoc_dung(self):
        ls, st = load(roles=("System Manager",), replies=[kie_ok()])
        self.assertTrue(ls.generate(REQ)["ok"])

    def test_de_bai_rong(self):
        ls, st = load()
        self.assertEqual(ls.generate(json.dumps({"task": ""}))["error"], "EMPTY_TASK")
        self.assertEqual(st["calls"], [])

    def test_prompt_bi_escape_duoc_go(self):
        ls, _ = load()
        self.assertEqual(ls.unescape_prompt("~ &amp; &lt; &gt;"), "~ & < >")


if __name__ == "__main__":
    unittest.main()
