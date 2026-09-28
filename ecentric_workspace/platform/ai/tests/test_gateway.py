# Copyright (c) 2026, eCentric and contributors
"""Cong AI chung: chuoi model, luat tep, ngan sach, log, quyen cua tro ly chat.

    python3 ecentric_workspace/platform/ai/tests/test_gateway.py

Chay ngoai Frappe: nap MA NGUON THAT bang exec voi `frappe` + `requests` gia (exec thay vi
import de __pycache__ khong vo hieu hoa dot bien).

HINH DANG PHAN HOI TRONG FILE NAY LA HINH DANG THAT:
  * than loi `{"code":500,"msg":"Server exception, please try again later"}` kem HTTP 200:
    chep tu C:\\dev\\probe_kie_fallback.ps1 chay 28/09 (ca gemini-3-8-flash lan 3-7-flash).
  * SSE Gemini cat JSON qua hai chunk: hinh dang do 22/09 (probe_kie_gemini.ps1).
  * than GPT Responses {"output":[{"type":"message","content":[{"type":"output_text"}]}]}:
    tai lieu docs.kie.ai/market/chat/gpt-5-5 + probe 28/09 tra 200.
"""
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.dirname(HERE)
KHOA = "kie-KHOA-BI-MAT-0123456789abcdef"


def sse(text, finish="STOP"):
    half = len(text) // 2
    out = ""
    for i, piece in enumerate((text[:half], text[half:])):
        cand = {"content": {"role": "model", "parts": [{"text": piece}]}}
        if i == 1:
            cand["finishReason"] = finish
        out += "data: " + json.dumps({"candidates": [cand]}, ensure_ascii=False) + "\n\n"
    return out + "data: " + json.dumps({"usageMetadata": {"totalTokenCount": 42}}) + "\n\n"


def gpt_body(text):
    return json.dumps({"output": [{"type": "reasoning", "summary": []},
                                  {"type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": text}]}],
                       "usage": {"total_tokens": 7}, "status": "completed"})


KIE_500 = '{"code":500,"msg":"Server exception, please try again later"}'


class Env(object):
    """Nap config/dialects/gateway/scope/chat/company_summary voi frappe gia."""

    def __init__(self, settings=None, conf=None):
        self.settings = {"ec_kie_api_key": KHOA, "ec_llm_model_kie": "gemini-3-8-flash",
                         "ec_llm_model_kie_fallback": "gpt-5-5"}
        self.settings.update(settings or {})
        self.logs, self.calls, self.replies, self.models_called = [], [], {}, []
        fk = types.ModuleType("frappe")
        env = self

        class _DB(object):
            def get_single_value(self, dt, f):
                return env.settings.get(f, "")
        fk.db = _DB()
        fk.conf = dict(conf or {})
        fk.log_error = lambda title=None, message=None, **k: env.logs.append((title, message))
        fk.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
        fk.session = types.SimpleNamespace(user="a@ecentric.vn")
        self.cache = {}

        class _Cache(object):
            def get_value(self, k):
                return env.cache.get(k)

            def set_value(self, k, v, expires_in_sec=None):
                env.cache[k] = v
                env.ttl = expires_in_sec

            def delete_value(self, k):
                env.cache.pop(k, None)
        fk.cache = lambda: _Cache()
        utils = types.ModuleType("frappe.utils")
        pw = types.ModuleType("frappe.utils.password")
        pw.get_decrypted_password = lambda *a, **k: env.settings.get("ec_kie_api_key", "")
        utils.password = pw
        fk.utils = utils
        sys.modules["frappe"] = fk
        sys.modules["frappe.utils"] = utils
        sys.modules["frappe.utils.password"] = pw
        rq = types.ModuleType("requests")
        rq.post = self._post
        sys.modules["requests"] = rq
        for pkg in ("ecentric_workspace", "ecentric_workspace.platform",
                    "ecentric_workspace.platform.ai"):
            sys.modules[pkg] = types.ModuleType(pkg)
        self.mod = {}
        for name in ("config", "dialects", "gateway", "scope", "chat", "company_summary"):
            full = "ecentric_workspace.platform.ai." + name
            m = types.ModuleType(full)
            m.__file__ = os.path.join(AI, name + ".py")
            sys.modules[full] = m
            setattr(sys.modules["ecentric_workspace.platform.ai"], name, m)
            with open(m.__file__, encoding="utf-8") as fh:
                exec(compile(fh.read(), m.__file__, "exec"), m.__dict__)
            self.mod[name] = m
        self.gw = self.mod["gateway"]

    def _post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "body": json, "timeout": timeout, "headers": headers})
        key = "gpt" if "codex" in url else ("grok" if "/grok/" in url else "gemini")
        model = json["model"] if key != "gemini" else url.split("/models/")[1].split(":")[0]
        self.models_called.append(model)
        reply = self.replies.get(model, self.replies.get(key))
        if callable(reply):
            reply = reply()
        if isinstance(reply, Exception):
            raise reply
        status, body = reply if reply else (200, KIE_500)
        return types.SimpleNamespace(status_code=status, content=body.encode("utf-8"))


SCHEMA = {"type": "object", "properties": {"diem": {"type": "integer"}}, "required": ["diem"]}


class Chuoi(unittest.TestCase):
    def test_chinh_song_thi_khong_goi_du_phong(self):
        e = Env()
        e.replies["gemini"] = (200, sse('{"diem": 7, "ly_do": "tot"}'))
        r = e.gw.generate("cham", schema=SCHEMA)
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["diem"], 7)
        self.assertEqual(r["model"], "gemini-3-8-flash")
        self.assertFalse(r["fell_back"])
        self.assertEqual(len(e.calls), 1)
        self.assertEqual(e.logs, [])

    def test_kie_bao_loi_bang_http_200_code_500_thi_roi_sang_gpt(self):
        e = Env()
        e.replies["gemini"] = (200, KIE_500)
        e.replies["gpt"] = (200, gpt_body('{"diem": 5}'))
        r = e.gw.generate("cham", schema=SCHEMA, purpose="t")
        self.assertTrue(r["ok"])
        self.assertEqual(r["model"], "gpt-5-5")
        self.assertTrue(r["fell_back"])
        self.assertIn("code=500", r["attempts"][0]["error"])
        self.assertEqual([t for t, _ in e.logs], ["ec_ai_fallback"])

    def test_gpt_nhan_loi_dan_json_va_schema(self):
        e = Env()
        e.replies["gpt"] = (200, gpt_body("```json\n{\"diem\": 5}\n```"))
        e.gw.generate("cham", schema=SCHEMA)
        body = e.calls[1]["body"]
        self.assertEqual(body["model"], "gpt-5-5")
        self.assertFalse(body["stream"])
        last = body["input"][-1]["content"][0]["text"]
        self.assertIn("JSON", last)
        self.assertIn('"diem"', last)

    def test_co_tep_thi_gpt_bi_bo_qua_khong_goi(self):
        e = Env()
        r = e.gw.generate("cham", schema=SCHEMA,
                          files=[{"data": b"%PDF-1.4", "mime_type": "application/pdf"}])
        self.assertFalse(r["ok"])
        self.assertTrue(all("codex" not in c["url"] for c in e.calls),
                        "gpt KHONG duoc goi khi co tep - no se tra loi tren du lieu thieu")
        self.assertIn("khong nhan tep", r["attempts"][1]["error"])
        self.assertEqual([t for t, _ in e.logs], ["ec_ai_failed"])

    def test_tep_thieu_bytes_thi_khong_goi_ai_ca(self):
        e = Env()
        r = e.gw.generate("cham", files=[{"uri": "files/x", "mime_type": "application/pdf"}])
        self.assertFalse(r["ok"])
        self.assertEqual(e.calls, [])

    def test_tep_di_inline_truoc_van_ban(self):
        e = Env()
        e.replies["gemini"] = (200, sse('{"diem": 9}'))
        r = e.gw.generate("cham", schema=SCHEMA,
                          files=[{"data": b"%PDF-1.4", "mime_type": "application/pdf"}])
        parts = e.calls[0]["body"]["contents"][-1]["parts"]
        self.assertIn("inlineData", parts[0])
        self.assertEqual(parts[-1]["text"], "cham")
        self.assertEqual(r["files_in_request"], 1)
        self.assertEqual(e.calls[0]["body"]["generationConfig"]["responseSchema"], SCHEMA)

    def test_json_cut_la_loi_cua_lan_thu_do(self):
        e = Env()
        e.replies["gemini"] = (200, sse('{"diem": 7, "ly_do": "'))
        e.replies["gpt"] = (200, gpt_body('{"diem": 6}'))
        r = e.gw.generate("cham", schema=SCHEMA)
        self.assertEqual(r["data"], {"diem": 6})
        self.assertIn("JSON", r["attempts"][0]["error"])

    def test_thieu_khoa_bat_buoc_la_loi(self):
        e = Env()
        e.replies["gemini"] = (200, sse('{"khac": 1}'))
        e.replies["gpt"] = (200, gpt_body('{"khac": 1}'))
        r = e.gw.generate("cham", schema=SCHEMA)
        self.assertFalse(r["ok"])
        self.assertIn("diem", r["attempts"][0]["error"])

    def test_treo_thi_thu_model_ke(self):
        e = Env()
        e.replies["gemini"] = TimeoutError("Read timed out")
        e.replies["gpt"] = (200, gpt_body("xin chao"))
        r = e.gw.generate("chao")
        self.assertEqual(r["text"], "xin chao")
        self.assertIn("Read timed out", r["attempts"][0]["error"])

    def test_khong_du_phong_thi_chi_mot_model(self):
        e = Env()
        r = e.gw.generate("chao", allow_fallback=False)
        self.assertEqual([c["url"].split("/")[-1] for c in e.calls],
                         ["gemini-3-8-flash:streamGenerateContent"])
        self.assertFalse(r["ok"])

    def test_tieng_viet_khong_vo(self):
        e = Env()
        e.replies["gemini"] = (200, sse("Chào anh chị, bông mềm."))
        self.assertEqual(e.gw.generate("x")["text"], "Chào anh chị, bông mềm.")


class NganSachVaCongTac(unittest.TestCase):
    def test_moi_lan_goi_deu_co_timeout_trong_ngan_sach(self):
        e = Env()
        e.gw.generate("x", budget=50, attempt_timeout=40)
        for c in e.calls:
            connect, read = c["timeout"]
            self.assertLessEqual(read, 50)
            self.assertLessEqual(read, 40)

    def test_het_ngan_sach_thi_khong_bat_dau_lan_thu_moi(self):
        e = Env()
        clock = [1000.0]
        e.gw.time = types.SimpleNamespace(time=lambda: clock[0])

        def slow():
            clock[0] += 95
            return (200, KIE_500)
        e.replies["gemini"] = slow
        r = e.gw.generate("x", budget=100)
        self.assertEqual(len(e.calls), 1)
        self.assertIn("het ngan sach", r["attempts"][1]["error"])

    def test_cong_tac_tat(self):
        e = Env(conf={"ec_ai_disabled": 1})
        r = e.gw.generate("x")
        self.assertEqual((r["ok"], r["error"], e.calls), (False, "ai_disabled", []))

    def test_khong_khoa(self):
        e = Env(settings={"ec_kie_api_key": ""})
        self.assertEqual(e.gw.generate("x")["error"], "no_key")
        self.assertEqual(e.calls, [])

    def test_khoa_mat_na_coi_nhu_khong_co(self):
        e = Env(settings={"ec_kie_api_key": "*" * 32})
        self.assertEqual(e.gw.generate("x")["error"], "no_key")

    def test_khoa_khong_lot_vao_loi(self):
        e = Env()
        e.replies["gemini"] = RuntimeError("401 cho khoa " + KHOA)
        r = e.gw.generate("x", allow_fallback=False)
        self.assertNotIn(KHOA, r["error"])
        self.assertNotIn(KHOA, json.dumps(e.logs))
        self.assertEqual(e.calls[0]["headers"]["Authorization"], "Bearer " + KHOA)

    def test_grok_cung_dinh_dang_responses_cong_rieng(self):
        # docs.kie.ai/market/grok/grok-4-7: POST /grok/v1/responses, than giong gpt
        e = Env(settings={"ec_llm_model_kie_fallback": "grok-4-7"})
        e.replies["grok"] = (200, gpt_body('{"diem": 3}'))
        r = e.gw.generate("cham", schema=SCHEMA)
        self.assertEqual((r["ok"], r["model"], r["data"]), (True, "grok-4-7", {"diem": 3}))
        call = e.calls[-1]
        self.assertEqual(call["url"], "https://api.kie.ai/grok/v1/responses")
        self.assertEqual(call["body"]["model"], "grok-4-7")
        self.assertIn("JSON", call["body"]["input"][-1]["content"][0]["text"])

    def test_grok_chua_do_tep_nen_khong_nhan_tep(self):
        e = Env(settings={"ec_llm_model_kie_fallback": "grok-4-7"})
        e.gw.generate("cham", files=[{"data": b"%PDF", "mime_type": "application/pdf"}])
        self.assertEqual(e.models_called, ["gemini-3-8-flash"])

    def test_ho_model_la_bi_bo_qua_co_ly_do(self):
        e = Env(settings={"ec_llm_model_kie_fallback": "claude-haiku-4-5"})
        r = e.gw.generate("x")
        self.assertIn("chua ho tro", r["attempts"][1]["error"])
        self.assertEqual(len(e.calls), 1)


class CauHinh(unittest.TestCase):
    def test_chuan_hoa_ten_model(self):
        c = Env().mod["config"]
        self.assertEqual(c.parse_models(" GPT-5-5 ,gpt-5-5; gemini-3-7-flash\n"),
                         ["gpt-5-5", "gemini-3-7-flash"])

    def test_du_phong_trung_model_chinh_bi_bo(self):
        c = Env(settings={"ec_llm_model_kie_fallback": "gemini-3-8-flash, gpt-5-5"}).mod["config"]
        self.assertEqual(c.chain(), ["gemini-3-8-flash", "gpt-5-5"])

    def test_mac_dinh(self):
        c = Env(settings={"ec_llm_model_kie": "", "ec_llm_model_kie_fallback": ""}).mod["config"]
        self.assertEqual(c.chain(), ["gemini-3-8-flash", "gemini-3-7-flash", "gemini-3-6-flash",
                                     "gpt-6-luna"])
        self.assertNotIn("gpt-5-5", c.chain(), "gpt-5-5 dat ~50 lan Luna - Hoan bo 28/09")

    def test_mac_dinh_co_tep_chi_roi_sang_gemini(self):
        e = Env(settings={"ec_llm_model_kie_fallback": ""})
        e.replies["gemini-3-6-flash"] = (200, sse('{"diem": 4}'))
        r = e.gw.generate("cham", schema=SCHEMA,
                          files=[{"data": b"%PDF-1.4", "mime_type": "application/pdf"}])
        self.assertTrue(r["ok"])
        self.assertEqual(e.models_called, ["gemini-3-8-flash", "gemini-3-7-flash",
                                           "gemini-3-6-flash"])
        self.assertEqual(r["model"], "gemini-3-6-flash")

    def test_mac_dinh_van_ban_toi_luna_khi_ca_ho_gemini_sap(self):
        e = Env(settings={"ec_llm_model_kie_fallback": ""})
        e.replies["gpt"] = (200, gpt_body("xin chao"))
        r = e.gw.generate("chao")
        self.assertEqual(r["model"], "gpt-6-luna")
        self.assertEqual(e.calls[-1]["body"]["model"], "gpt-6-luna")


class NhoModelSap(unittest.TestCase):
    """28/09: Kie treo ~34s roi 500, cac ban Gemini sap cung luc. Khong nho thi moi lan goi
    deu cho 34s x tung ban truoc khi toi model con song."""

    def test_phan_loai_loi(self):
        gw = Env().gw
        for err in ("Kie code=500: Server exception", "HTTP 502", "HTTP 429: cham lai",
                    "HTTP 500: Kie code=500: x", "ReadTimeout: read timed out",
                    "TimeoutError: Read timed out", "ConnectionError: reset"):
            self.assertTrue(gw.is_outage(err), err)
        for err in ("khong doc duoc JSON (finish=STOP)", "JSON thieu khoa bat buoc: diem",
                    "HTTP 400: bad", "HTTP 401", "model tra ve rong (finish=MAX_TOKENS)",
                    "Kie loi: invalid model", "Kie code=422: sai tham so", ""):
            self.assertFalse(gw.is_outage(err), err)

    def test_model_sap_bi_bo_qua_o_lan_goi_sau(self):
        e = Env()
        e.replies["gemini"] = (200, KIE_500)
        e.replies["gpt"] = (200, gpt_body("ok"))
        e.gw.generate("lan 1")
        self.assertEqual(e.ttl, e.gw.DOWN_SECONDS)
        e.models_called[:] = []
        r = e.gw.generate("lan 2")
        self.assertTrue(r["ok"])
        self.assertEqual(e.models_called, ["gpt-5-5"], "khong cho 34s lan nua o model dang sap")
        self.assertIn("vua sap", r["attempts"][0]["error"])
        self.assertTrue(r["fell_back"])

    def test_loi_noi_dung_khong_danh_dau_sap(self):
        e = Env()
        e.replies["gemini"] = (200, sse('{"diem": 7, "ly_do": "'))
        e.replies["gpt"] = (200, gpt_body('{"diem": 6}'))
        e.gw.generate("cham", schema=SCHEMA)
        self.assertEqual(e.cache, {}, "JSON hong la loi cua cau hoi nay, khong phai model sap")

    def test_moi_model_dung_duoc_deu_nghi_thi_van_thu(self):
        e = Env()
        e.cache[e.gw.DOWN_KEY % "gemini-3-8-flash"] = 1
        e.replies["gemini"] = (200, sse('{"diem": 8}'))
        r = e.gw.generate("cham", schema=SCHEMA,
                          files=[{"data": b"%PDF", "mime_type": "application/pdf"}])
        self.assertTrue(r["ok"], "chi con gemini mang duoc tep - bo nho khong duoc chan het")
        self.assertEqual(e.models_called, ["gemini-3-8-flash"])

    def test_ca_kie_sap_thi_chi_thu_mot_model(self):
        # probe 28/09 chieu: 3 ban Gemini treo 34s roi 500, luna 500, gpt-5-5 treo 120s
        e = Env(settings={"ec_llm_model_kie_fallback": ""})
        for m in ("gemini-3-8-flash", "gemini-3-7-flash", "gemini-3-6-flash", "gpt-6-luna"):
            e.cache[e.gw.DOWN_KEY % m] = 1
        r = e.gw.generate("chao")
        self.assertFalse(r["ok"])
        self.assertEqual(e.models_called, ["gemini-3-8-flash"],
                         "ca Kie sap: mot lan 34s, khong phai 34s x 4")

    def test_song_lai_thi_xoa_dau(self):
        e = Env()
        e.cache[e.gw.DOWN_KEY % "gemini-3-8-flash"] = 1
        e.replies["gemini"] = (200, sse("chao"))
        e.gw.generate("x", models=["gemini-3-8-flash"])
        self.assertEqual(e.cache, {})

    def test_models_truyen_tay_bo_qua_bo_nho(self):
        e = Env()
        e.cache[e.gw.DOWN_KEY % "gemini-3-8-flash"] = 1
        e.replies["gpt"] = (200, gpt_body("ok"))
        e.gw.generate("x", models=["gemini-3-8-flash", "gpt-5-5"])
        self.assertEqual(e.models_called, ["gemini-3-8-flash", "gpt-5-5"],
                         "probe / AI Content chi dinh model thi phai goi that")

    def test_khong_co_cache_van_chay(self):
        e = Env()
        del sys.modules["frappe"].cache
        e.replies["gemini"] = (200, sse("chao"))
        self.assertTrue(e.gw.generate("x")["ok"])


class Quyen(unittest.TestCase):
    """A14: KHONG suy quyen tu chuc danh."""

    def setUp(self):
        self.s = Env().mod["scope"]

    def test_truong_nhom_KHONG_duoc_xem_ca_cong_ty(self):
        v = self.s.decide("lead@x", None, {"name": "E1", "department": "Media - EC"}, [], [])
        self.assertEqual((v["scope"], v["depts"]), ("dept", ["Media - EC"]))

    def test_management_xem_ca_cong_ty(self):
        v = self.s.decide("m@x", None, {"name": "E2", "department": "Management - EC"}, [], [])
        self.assertEqual(v["scope"], "all")
        v = self.s.decide("m@x", None, {"name": "E2", "department": "Media - EC"},
                          ["Management - EC"], [])
        self.assertEqual(v["scope"], "all")

    def test_viewer_permission(self):
        self.assertEqual(self.s.decide("v@x", {"scope": "all"}, None, [], [])["scope"], "all")
        v = self.s.decide("v@x", {"scope": "dept", "custom_department": "HR - EC"}, None, [], [])
        self.assertEqual((v["scope"], v["depts"]), ("dept", ["HR - EC"]))

    def test_truong_phong_thay_ca_phong_minh_quan_ly(self):
        v = self.s.decide("t@x", None, {"name": "E3", "department": "Media - EC"}, [],
                          ["Content - EC", "Media - EC"])
        self.assertEqual(v["depts"], ["Media - EC", "Content - EC"])

    def test_khong_phong_ban_thi_chi_minh(self):
        self.assertEqual(self.s.decide("n@x", None, {"name": "E4"}, [], [])["scope"], "self")
        self.assertEqual(self.s.decide("Guest", {"scope": "all"}, None, [], [])["scope"], "self")


class TroLyChat(unittest.TestCase):
    def test_lich_su_duoc_giu_va_cat(self):
        c = Env().mod["chat"]
        h = [{"role": "user", "text": "a"}, {"role": "model", "text": "b"}, {"role": "x"},
             "rac"] + [{"role": "user", "text": str(i)} for i in range(20)]
        out = c.clean_history(h)
        self.assertLessEqual(len(out), c.MAX_HISTORY_TURNS)
        self.assertTrue(all(set(x) == {"role", "text"} for x in out))
        self.assertEqual(c.clean_history(json.dumps([{"role": "model", "text": "b"}])),
                         [{"role": "model", "text": "b"}])

    def test_lich_su_vao_request_nhieu_luot(self):
        e = Env()
        e.replies["gemini"] = (200, sse("ok"))
        e.gw.generate("phong kia thi sao?", history=[{"role": "user", "text": "phong Media?"},
                                                     {"role": "model", "text": "Media on."}])
        roles = [x["role"] for x in e.calls[0]["body"]["contents"]]
        self.assertEqual(roles, ["user", "model", "user"])

    def test_tuan_dau_nam(self):
        import datetime
        c = Env().mod["chat"]
        self.assertEqual(c.week_labels(datetime.datetime(2027, 1, 6)), ("2027-W01", "2026-W53"))
        self.assertEqual(c.week_labels(datetime.datetime(2026, 9, 28)), ("2026-W40", "2026-W39"))


class TongHopCongTy(unittest.TestCase):
    def test_quyen_xem(self):
        cs = Env().mod["company_summary"]
        self.assertTrue(cs.can_view({"scope": "all", "depts": []}, ""))
        self.assertFalse(cs.can_view({"scope": "dept", "depts": ["A"]}, ""))
        self.assertTrue(cs.can_view({"scope": "dept", "depts": ["A"]}, "A"))
        self.assertFalse(cs.can_view({"scope": "dept", "depts": ["A"]}, "B"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
