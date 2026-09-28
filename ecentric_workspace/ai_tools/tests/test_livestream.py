# Copyright (c) 2026, eCentric and contributors
"""Endpoint sinh script AI Livestream, qua CONG AI CHUNG (28/09).

    python3 ecentric_workspace/ai_tools/tests/test_livestream.py

Chay ngoai Frappe: nap livestream.py VA ca bo platform/ai THAT (config, dialects, gateway)
bang exec voi `frappe` + `requests` gia. Test di xuyen tu endpoint toi than HTTP.

Luat quan trong nhat (Vinh chot 23/09): model chinh hong thi KHONG tu doi model - tra
KIE_LOI de NGUOI DUNG chon. Chi khi ho bam "van viet bang model khac" moi chay du phong.
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
AI = os.path.join(APP, "platform", "ai")

GOOD = {"parts": {"intro": "Chào anh chị.", "ksp": "Bông mềm.", "howto": "Thấm ướt.",
                  "cta": "Chốt đơn nha."}, "claims_used": []}
KIE_500 = '{"code":500,"msg":"Server exception, please try again later"}'


def sse(text):
    """Than SSE kieu Kie: van ban CAT DOI qua hai chunk (hinh dang that do 22/09)."""
    half = len(text) // 2
    out = ""
    for i, piece in enumerate((text[:half], text[half:])):
        cand = {"content": {"role": "model", "parts": [{"text": piece}]}}
        if i == 1:
            cand["finishReason"] = "STOP"
        out += "data: " + json.dumps({"candidates": [cand]}, ensure_ascii=False) + "\n\n"
    return out + "data: " + json.dumps({"usageMetadata": {"totalTokenCount": 9000}}) + "\n\n"


def gpt(text):
    return json.dumps({"output": [{"type": "message", "content": [
        {"type": "output_text", "text": text}]}], "usage": {"total_tokens": 777},
        "status": "completed"})


def load(settings=None, roles=("EC AI Content",), replies=None, conf=None):
    st = {"settings": dict({"ec_ail_prompt": "PROMPT", "ec_kie_api_key": "KIEKEY",
                            "ec_llm_model_kie": "gemini-3-8-flash",
                            "ec_llm_model_kie_fallback": "gpt-5-5"}, **(settings or {})),
          "calls": [], "logs": [], "replies": dict(replies or {})}
    fk = types.ModuleType("frappe")

    class _DB(object):
        def get_single_value(self, dt, field):
            return st["settings"].get(field, "")
    fk.db = _DB()
    fk.conf = dict(conf or {})
    fk.session = types.SimpleNamespace(user="content@ecentric.vn")
    fk.get_roles = lambda user=None: list(roles)
    fk.log_error = lambda *a, **k: st["logs"].append(k.get("title") or (a[0] if a else ""))
    fk.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    utils = types.ModuleType("frappe.utils")
    utils.now = lambda: "2026-09-28 13:00:00.123456"
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda dt, name, field, **k: st["settings"].get(field, "")
    utils.password = pw
    fk.utils = utils
    rq = types.ModuleType("requests")

    def _post(url, json=None, timeout=None, headers=None):
        st["calls"].append({"url": url, "body": json, "timeout": timeout})
        r = st["replies"].get("gpt" if "codex" in url else "gemini")
        if r is None:
            raise AssertionError("goi HTTP ngoai du kien: %s" % url)
        if isinstance(r, Exception):
            raise r
        return types.SimpleNamespace(status_code=r[0], content=r[1].encode("utf-8"))
    rq.post = _post
    sys.modules.update({"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw,
                        "requests": rq})
    for pkg in ("ecentric_workspace", "ecentric_workspace.platform", "ecentric_workspace.platform.ai"):
        sys.modules[pkg] = types.ModuleType(pkg)
    for name in ("config", "dialects", "gateway"):
        full = "ecentric_workspace.platform.ai." + name
        m = types.ModuleType(full)
        sys.modules[full] = m
        setattr(sys.modules["ecentric_workspace.platform.ai"], name, m)
        path = os.path.join(AI, name + ".py")
        with io.open(path, encoding="utf-8") as fh:
            exec(compile(fh.read(), path, "exec"), m.__dict__)
    ls = types.ModuleType("livestream_under_test")
    with io.open(SRC_LS, encoding="utf-8") as fh:
        exec(compile(fh.read(), SRC_LS, "exec"), ls.__dict__)
    return ls, st


REQ = json.dumps({"task": "DE BAI", "preset": "full"})
REQ_KHAC = json.dumps({"task": "DE BAI", "provider": "google"})


class TestDuongChinh(unittest.TestCase):
    def test_model_chinh_ok(self):
        ls, st = load(replies={"gemini": (200, sse(json.dumps(GOOD, ensure_ascii=False)))})
        r = ls.generate(REQ)
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"], GOOD, "tieng Viet phai nguyen ven sau khi noi chunk")
        self.assertEqual((r["model"], r["provider"], r["fell_back"], r["tokens"]),
                         ("gemini-3-8-flash", "kie", False, 9000))
        self.assertEqual(len(st["calls"]), 1)

    def test_cau_hinh_duoc_giu(self):
        ls, st = load(replies={"gemini": (200, sse(json.dumps(GOOD)))})
        ls.generate(REQ)
        body = st["calls"][0]["body"]
        cfg = body["generationConfig"]
        # thinking BAT - tat thinking tung lam so luat bi pha tang 4 -> 13 (17/09)
        self.assertEqual(cfg["thinkingConfig"]["thinkingBudget"], 2048)
        self.assertEqual(cfg["maxOutputTokens"], 32000)
        self.assertEqual(cfg["temperature"], 0.4)
        self.assertEqual(cfg["responseMimeType"], "application/json")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "PROMPT")


class TestKhongTuDoiModel(unittest.TestCase):
    def test_model_chinh_hong_thi_KIE_LOI_va_KHONG_goi_du_phong(self):
        ls, st = load(replies={"gemini": (200, KIE_500), "gpt": (200, gpt(json.dumps(GOOD)))})
        r = ls.generate(REQ)
        self.assertEqual((r["ok"], r["error"], r["model"]), (False, "KIE_LOI", "gemini-3-8-flash"))
        self.assertIn("code=500", r["detail"])
        self.assertTrue(all("codex" not in c["url"] for c in st["calls"]))

    def test_json_cut_cung_la_KIE_LOI(self):
        ls, st = load(replies={"gemini": (200, sse('{"parts": {"intro": "Ch'))})
        r = ls.generate(REQ)
        self.assertEqual(r["error"], "KIE_LOI")
        self.assertIn("JSON", r["detail"])

    def test_nguoi_dung_chon_model_khac_thi_chay_du_phong(self):
        ls, st = load(replies={"gpt": (200, gpt(json.dumps(GOOD, ensure_ascii=False)))})
        r = ls.generate(REQ_KHAC)
        self.assertTrue(r["ok"])
        self.assertEqual((r["model"], r["fell_back"], r["tokens"]), ("gpt-5-5", True, 777))
        self.assertTrue(all("gemini" not in c["url"] for c in st["calls"]),
                        "da chon model khac thi khong goi lai model chinh")

    def test_allow_fallback_cung_chay_du_phong(self):
        ls, _ = load(replies={"gpt": (200, gpt(json.dumps(GOOD)))})
        self.assertTrue(ls.generate(json.dumps({"task": "x", "allow_fallback": True}))["ok"])

    def test_du_phong_cung_hong_thi_bao_loi_co_log(self):
        ls, st = load(replies={"gpt": (500, '{"error":{"type":"server_error"}}')})
        r = ls.generate(REQ_KHAC)
        self.assertEqual(r["error"], "GEMINI_CALL_FAILED")
        self.assertIn("ec_ail_generate GEMINI_CALL_FAILED", st["logs"])


class TestTran(unittest.TestCase):
    def test_moi_lan_goi_co_timeout_va_tong_duoi_120s(self):
        ls, st = load(replies={"gemini": (200, sse(json.dumps(GOOD)))})
        ls.generate(REQ)
        self.assertLess(ls.BUDGET, 120)
        self.assertLessEqual(st["calls"][0]["timeout"][1], ls.BUDGET)


class TestCong(unittest.TestCase):
    def test_khong_co_role_thi_khong_goi_http(self):
        ls, st = load(roles=("Employee",))
        self.assertEqual(ls.generate(REQ)["error"], "NO_ROLE")
        self.assertEqual(st["calls"], [])

    def test_system_manager_duoc_dung(self):
        ls, _ = load(roles=("System Manager",), replies={"gemini": (200, sse(json.dumps(GOOD)))})
        self.assertTrue(ls.generate(REQ)["ok"])

    def test_de_bai_rong(self):
        ls, st = load()
        self.assertEqual(ls.generate(json.dumps({"task": ""}))["error"], "EMPTY_TASK")
        self.assertEqual(st["calls"], [])

    def test_prompt_rong(self):
        ls, st = load(settings={"ec_ail_prompt": ""})
        self.assertEqual(ls.generate(REQ)["error"], "NO_PROMPT")

    def test_cong_tac_tat_AI(self):
        ls, st = load(conf={"ec_ai_disabled": 1})
        self.assertEqual(ls.generate(REQ)["error"], "AI_TAT")
        self.assertEqual(st["calls"], [])

    def test_prompt_bi_escape_duoc_go(self):
        ls, _ = load()
        self.assertEqual(ls.unescape_prompt("~ &amp; &lt; &gt;"), "~ & < >")


if __name__ == "__main__":
    unittest.main()
