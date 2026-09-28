# -*- coding: utf-8 -*-
"""`gemini_api.generate_json` sau 28/09: chi con la cua vao CONG AI CHUNG.

    python3 ecentric_workspace/approval_center/tests/standalone/test_llm_provider.py

Truoc 28/09 file nay kiem lop Kie + du phong Google ben trong gemini_api (28 test tren than
SSE that). Lop do da chuyen sang `platform/ai/` va cac luat cua no - noi chunk SSE, bat loi
HTTP 200 + code 500, tep inline dat truoc van ban, khong gui thieu tep, JSON hong la loi -
nay nam o `platform/ai/tests/test_gateway.py`, CUNG than that.

O day chi con mot viec: generate_json (AI dien ho + cham diem goi no) chuyen DUNG tham so
xuong cong va tra ve DUNG hinh dang nguoi goi cu doc. Sai mot khoa o day thi AI dien ho
nhan `ok=True` voi `data=None`, hoac `no_key` bien thanh mot loi chung chung.

Chay ngoai Frappe: nap gemini_api.py bang exec voi `frappe` gia va cong gia.
"""
import io
import os
import sys
import types
import unittest

REPO = os.environ.get("REPO", ".")
SRC = os.path.join(REPO, "ecentric_workspace", "gemini_api.py")


def load(result):
    """-> (module, calls). `result` = dict cong gia tra ve."""
    calls = []
    fk = types.ModuleType("frappe")
    fk.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    fk.db = types.SimpleNamespace(get_single_value=lambda *a: "")
    fk.log_error = lambda **k: None
    fk.only_for = lambda *a: None
    sys.modules["frappe"] = fk
    gw = types.ModuleType("ecentric_workspace.platform.ai.gateway")

    def generate(prompt, **kw):
        calls.append(dict(kw, prompt=prompt))
        return dict(result)
    gw.generate = generate
    pkg = types.ModuleType("ecentric_workspace.platform.ai")
    pkg.gateway = gw
    for name, mod in (("ecentric_workspace", types.ModuleType("ecentric_workspace")),
                      ("ecentric_workspace.platform", types.ModuleType("ecentric_workspace.platform")),
                      ("ecentric_workspace.platform.ai", pkg),
                      ("ecentric_workspace.platform.ai.gateway", gw)):
        sys.modules[name] = mod
    sys.modules["requests"] = types.ModuleType("requests")
    m = types.ModuleType("gemini_api_under_test")
    m.__file__ = SRC
    exec(compile(io.open(SRC, encoding="utf-8").read(), SRC, "exec"), m.__dict__)
    return m, calls


OK = {"ok": True, "text": '{"a": 1}', "data": {"a": 1}, "model": "gemini-3-8-flash",
      "fell_back": False, "error": "", "attempts": [{"model": "gemini-3-8-flash", "ok": True}],
      "latency_ms": 12, "files_in_request": 1, "usage": {}, "finish": "STOP"}


class TestCuaVaoCong(unittest.TestCase):
    def test_tham_so_di_xuong_cong(self):
        m, calls = load(OK)
        files = [{"data": b"%PDF", "mime_type": "application/pdf"}]
        m.generate_json("P", {"type": "object"}, system_instruction="S", files=files,
                        budget=200, timeout=150, purpose="weekly_report")
        c = calls[0]
        self.assertEqual((c["prompt"], c["system"], c["schema"]), ("P", "S", {"type": "object"}))
        self.assertIs(c["files"], files)
        self.assertEqual((c["budget"], c["attempt_timeout"], c["purpose"]),
                         (200, 150, "weekly_report"))
        self.assertIsNone(c["models"], "khong ep model thi cong tu chon chuoi")

    def test_ep_model_thi_chi_mot_model(self):
        m, calls = load(OK)
        m.generate_json("P", {}, model="gpt-5-5")
        self.assertEqual(calls[0]["models"], ["gpt-5-5"])

    def test_hinh_dang_tra_ve_nguoi_goi_cu_doc(self):
        m, _ = load(OK)
        r = m.generate_json("P", {})
        for k in ("ok", "data", "error", "model", "latency_ms", "provider", "fell_back",
                  "files_in_request"):
            self.assertIn(k, r)
        self.assertEqual((r["ok"], r["data"], r["error"], r["provider"]),
                         (True, {"a": 1}, None, "kie"))

    def test_no_key_giu_nguyen_de_AI_dien_ho_bao_dung(self):
        m, _ = load(dict(OK, ok=False, data=None, error="no_key", attempts=[]))
        r = m.generate_json("P", {})
        self.assertEqual((r["ok"], r["error"]), (False, "no_key"))

    def test_hong_ca_chuoi_thi_bao_ly_do_va_model_cuoi(self):
        att = [{"model": "gemini-3-8-flash", "ok": False, "error": "Kie code=500"},
               {"model": "gpt-5-5", "ok": False, "error": "HTTP 500"}]
        m, _ = load(dict(OK, ok=False, data=None, model="", error="x: Kie code=500 | y",
                         attempts=att))
        r = m.generate_json("P", {})
        self.assertFalse(r["ok"])
        self.assertIn("code=500", r["error"])
        self.assertEqual(r["model"], "gpt-5-5")

    def test_khong_con_duong_google(self):
        src = io.open(SRC, encoding="utf-8").read()
        tail = src[src.find("def generate_json("):]
        self.assertNotIn("generativelanguage", tail)
        self.assertNotIn("_call_google", src)
        self.assertEqual(load(OK)[0].provider(), "kie")


if __name__ == "__main__":
    unittest.main(verbosity=1)
