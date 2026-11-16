# Copyright (c) 2026, eCentric and contributors
"""Giong doc AI (eVoice tren ERP): luat thuan + client HTTP (session gia). Chay khong can Frappe:
    python -m unittest ecentric_workspace.ai_tools.tests.test_ai_voice_domain"""
import datetime
import json
import unittest

from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure import evoice_client as EC

USER = ("EC AI Voice User",)
MANAGER = ("EC AI Voice Manager",)
ADMIN = ("System Manager",)


class TestPermissions(unittest.TestCase):
    def test_role_tiers(self):
        self.assertTrue(R.is_user(USER) and R.is_user(("EC AI Content",)) and R.is_user(MANAGER))
        self.assertFalse(R.is_user(("Employee", "Guest")))
        self.assertTrue(R.is_manager(("EC AI Video Admin",)) and not R.is_manager(USER))
        self.assertTrue(R.is_admin(ADMIN) and not R.is_admin(MANAGER))
        with self.assertRaises(C.AiVoicePermission):
            R.require_user(("Guest",))
        with self.assertRaises(C.AiVoicePermission):
            R.require_manager(USER)
        with self.assertRaises(C.AiVoicePermission):
            R.require_admin(MANAGER)

    def test_job_owner_or_manager(self):
        job = {"owner": "a@x"}
        self.assertTrue(R.can_touch_job(job, "a@x", USER))
        self.assertFalse(R.can_touch_job(job, "b@x", USER))
        self.assertTrue(R.can_touch_job(job, "b@x", MANAGER))
        self.assertFalse(R.can_touch_job(None, "a@x", MANAGER))

    def test_profile_usage(self):
        p = {"status": "active", "voice_id": "v1", "restricted": 0}
        self.assertTrue(R.can_use_profile(p, "u@x", USER))
        self.assertFalse(R.can_use_profile(dict(p, status="disabled"), "u@x", USER))
        self.assertFalse(R.can_use_profile(dict(p, voice_id=""), "u@x", USER), "chua co ma giong tren may")
        r = dict(p, restricted=1, owner_user="o@x")
        self.assertFalse(R.can_use_profile(r, "u@x", USER))
        self.assertTrue(R.can_use_profile(r, "o@x", USER))
        self.assertTrue(R.can_use_profile(r, "u@x", MANAGER))
        self.assertFalse(R.can_use_profile(dict(p, missing_on_server=1), "u@x", MANAGER), "may mat giong")


class TestText(unittest.TestCase):
    def test_keeps_phonetic_spelling(self):
        t = "  Xin chào cả nhà, hôm nay mình lên sóng với sì-kin-ke Cô-rê-a\r\nGiá chỉ 199k  "
        self.assertEqual(R.validate_text(t), "Xin chào cả nhà, hôm nay mình lên sóng với sì-kin-ke Cô-rê-a\nGiá chỉ 199k")

    def test_empty_symbols_too_long(self):
        for bad in (None, "", "   \n "):
            with self.assertRaises(C.AiVoiceError):
                R.validate_text(bad)
        with self.assertRaises(C.AiVoiceError):
            R.validate_text("... !!! ---")
        with self.assertRaises(C.AiVoiceError) as cm:
            R.validate_text("a" * (C.MAX_CHARS + 1))
        self.assertIn(str(C.MAX_CHARS), str(cm.exception))
        self.assertEqual(len(R.validate_text("a" * C.MAX_CHARS)), C.MAX_CHARS)

    def test_params(self):
        self.assertEqual(R.norm_quality(""), C.DEFAULT_QUALITY)
        self.assertEqual(R.norm_quality("quality_ultra"), "quality_ultra")
        with self.assertRaises(C.AiVoiceError):
            R.norm_quality("fast; drop table")
        self.assertEqual(R.norm_speed(None), C.SPEED_DEFAULT)
        self.assertEqual(R.norm_speed("1.234"), 1.23)
        for bad in ("abc", "nan", "0.1", "3", "inf"):
            with self.assertRaises(C.AiVoiceError):
                R.norm_speed(bad)
        self.assertEqual(R.norm_language(""), "vi")
        with self.assertRaises(C.AiVoiceError):
            R.norm_language("xx")

    def test_title(self):
        self.assertEqual(R.norm_title("  A   b ", "x"), "A b")
        t = R.norm_title("", "Một câu rất dài " * 10)
        self.assertTrue(t.endswith("…") and len(t) <= 61)
        self.assertEqual(len(R.norm_title("x" * 500, "y")), C.MAX_TITLE)

    def test_payload(self):
        job = {"name": "J1", "text": "chào", "voice_key": "brand:Lix", "quality": "quality_fast", "speed": 1.1,
               "language": "vi", "breath": 0}
        p = R.job_payload(job, "https://erp/cb")
        self.assertEqual(p["ref"], "J1")
        self.assertEqual(p["format"], "mp3")
        self.assertIs(p["breath"], False)
        self.assertEqual(p["callback_url"], "https://erp/cb")
        self.assertNotIn("callback_url", R.job_payload(job, ""))


class TestRemoteStatus(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(R.remote_update({"status": "weird"}), {})
        self.assertEqual(R.remote_update(None), {})
        q = R.remote_update({"status": "queued", "position": "3"})
        self.assertEqual((q["status"], q["position"]), ("queued", 3))
        r = R.remote_update({"status": "running", "progress": "2/5", "position": 4})
        self.assertEqual((r["progress"], r["position"]), ("2/5", 0))
        d = R.remote_update({"status": "done", "seconds": "12.345", "gen_seconds": "nan"})
        self.assertEqual(d["seconds"], 12.35)
        self.assertNotIn("gen_seconds", d)
        e = R.remote_update({"status": "error", "error": ""})
        self.assertTrue(e["error"])
        self.assertEqual(R.remote_update({"status": "cancelled"})["error"], C.Msg.CANCELLED)

    def test_never_moves_back(self):
        self.assertTrue(R.is_stale_update("done", "running"))
        self.assertTrue(R.is_stale_update("error", "done"))
        self.assertTrue(R.is_stale_update("running", "queued"))
        self.assertFalse(R.is_stale_update("queued", "running"))
        self.assertFalse(R.is_stale_update("running", "done"))
        self.assertFalse(R.is_stale_update("pending", "error"))


class TestSignature(unittest.TestCase):
    def test_hmac(self):
        body = json.dumps({"id": "a", "status": "done"}).encode()
        sig = R.sign("tok", body)
        self.assertTrue(R.verify_signature("tok", body, sig))
        self.assertTrue(R.verify_signature("tok", body, sig.upper()))
        self.assertFalse(R.verify_signature("tok", body + b" ", sig))
        self.assertFalse(R.verify_signature("other", body, sig))
        self.assertFalse(R.verify_signature("", body, R.sign("", body)), "chua co token -> tu choi het")
        self.assertFalse(R.verify_signature("tok", body, ""))
        self.assertFalse(R.verify_signature("tok", "str-not-bytes", sig))


class TestVoiceRules(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(R.validate_voice_fields("  Lan   Bắc ", "Nữ", " d "), ("Lan Bắc", "Nữ", "d"))
        with self.assertRaises(C.AiVoiceError):
            R.validate_voice_fields("", "Nữ", "")
        with self.assertRaises(C.AiVoiceError):
            R.validate_voice_fields("x" * 81, "Nữ", "")
        with self.assertRaises(C.AiVoiceError):
            R.validate_voice_fields("Lan", "Robot", "")
        self.assertEqual(len(R.validate_voice_fields("a", "", "d" * 999)[2]), C.MAX_DESC)

    def test_sample_file(self):
        self.assertEqual(R.validate_sample_file("Giọng.MP3", 1000), ".mp3")
        for bad in ("a.exe", "noext", "", None, "a.mp3.php"):
            with self.assertRaises(C.AiVoiceError):
                R.validate_sample_file(bad, 10)
        with self.assertRaises(C.AiVoiceError):
            R.validate_sample_file("a.wav", C.MAX_VOICE_BYTES + 1)

    def test_consent(self):
        self.assertEqual(R.validate_consent(" Nguyễn  Lan ", "2026-11-01", "1"), ("Nguyễn Lan", "2026-11-01"))
        for args in (("", "2026-11-01", 1), ("Lan", "", 1), ("Lan", "2026-11-01", 0), ("Lan", "2026-11-01", "false")):
            with self.assertRaises(C.AiVoiceError):
                R.validate_consent(*args)
        for bad in ("01/11/2026", "2026-13-01", "2026-02-30"):
            with self.assertRaises(C.AiVoiceError):
                R.validate_consent("Lan", bad, 1)

    def test_base_url(self):
        self.assertEqual(R.norm_base_url(" https://voice.ecentric.asia/ "), "https://voice.ecentric.asia")
        self.assertEqual(R.norm_base_url("http://192.168.1.5:7895"), "http://192.168.1.5:7895")
        for bad in ("voice.ecentric.asia", "ftp://x", "https://x.y/a?b=1", "javascript:alert(1)", "https://a b"):
            with self.assertRaises(C.AiVoiceError):
                R.norm_base_url(bad)

    def test_match_remote_voice(self):
        remote = [{"id": "v1", "name": "Lan", "description": "giong cu [erp:abc123]"}, {"id": "v2", "name": "Lan"},
                  {"id": "v3", "name": "Lan", "description": "[erp:abc123x]"}]
        self.assertEqual(R.match_remote_voice(remote, "abc123", set()), "v1")
        self.assertIsNone(R.match_remote_voice(remote, "abc123", {"v1"}))
        self.assertIsNone(R.match_remote_voice(remote, "zzz", set()), "khong doan theo ten")
        self.assertIsNone(R.match_remote_voice(None, "abc123", set()))
        self.assertEqual(R.with_marker("Giọng trẻ", "abc"), "Giọng trẻ [erp:abc]")
        self.assertEqual(R.with_marker("x [erp:abc]", "abc"), "x [erp:abc]")
        self.assertEqual(R.strip_marker("Giọng trẻ [erp:abc]"), "Giọng trẻ")

    def test_callback_base(self):
        self.assertEqual(R.callback_base("http://team.ecentric.vn/"), "https://team.ecentric.vn")
        self.assertEqual(R.callback_base("http://localhost:8000"), "http://localhost:8000")
        self.assertEqual(R.callback_base("http://192.168.1.2"), "http://192.168.1.2")
        self.assertEqual(R.callback_base("team.ecentric.vn"), "")
        self.assertEqual([R.fetch_backoff_seconds(a) for a in (0, 1, 3, 9)], [0, 120, 480, 3600])


class TestTime(unittest.TestCase):
    def test_parse_age_backoff(self):
        now = datetime.datetime(2026, 11, 15, 10, 0, 0)
        self.assertEqual(R.age_seconds("2026-11-15 09:59:00.123456", now), 59.876544)
        self.assertEqual(R.age_seconds("2026-11-15T09:58:00", now), 120)
        self.assertGreater(R.age_seconds(None, now), 10 ** 8)
        self.assertGreater(R.age_seconds("rac", now), 10 ** 8)
        self.assertEqual([R.submit_backoff_seconds(a) for a in (0, 1, 2, 3, 4, 5, 9)], [0, 120, 240, 480, 960, 1800, 1800])


# ------------------------------------------------------------------ client HTTP (session gia) ---
class FakeResp:
    def __init__(self, status, body=None, headers=None, chunks=None, text=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self._chunks, self.text, self.closed = chunks, text if text is not None else (json.dumps(body) if body is not None else ""), False

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_content(self, n):
        for c in self._chunks or []:
            if isinstance(c, Exception):
                raise c
            yield c

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if self.exc:
            raise self.exc
        return self.resp


class TestClient(unittest.TestCase):
    def setUp(self):
        # requests gia: may chay test co the khong cai requests, hoac test khac da thay sys.modules["requests"].
        import sys
        import types
        req = types.ModuleType("requests")
        req.RequestException = type("RequestException", (IOError,), {})
        req.ConnectionError = type("ConnectionError", (req.RequestException,), {})
        req.Timeout = type("Timeout", (req.RequestException,), {})
        saved = sys.modules.get("requests")
        sys.modules["requests"] = req
        self.addCleanup(lambda: sys.modules.__setitem__("requests", saved) if saved else sys.modules.pop("requests", None))
        self.req = req

    def cli(self, resp=None, exc=None):
        s = FakeSession(resp, exc)
        return EC.EVoiceClient("https://voice.x/", "tok", timeout=7, session=s), s

    def test_bearer_and_no_redirect(self):
        c, s = self.cli(FakeResp(200, {"ready": True}))
        self.assertEqual(c.health(), {"ready": True})
        method, url, kw = s.calls[0]
        self.assertEqual((method, url), ("GET", "https://voice.x/health"))
        self.assertEqual(kw["headers"]["Authorization"], "Bearer tok")
        self.assertIs(kw["allow_redirects"], False)
        self.assertEqual(kw["timeout"], 7)

    def test_tunnel_down_codes(self):
        for code in (502, 530, 524):
            c, _ = self.cli(FakeResp(code, text="<html>cloudflare</html>"))
            with self.assertRaises(EC.EVoiceDown) as cm:
                c.voices()
            self.assertEqual(cm.exception.timeout, code == 524)

    def test_network_errors(self):
        requests = self.req
        c, _ = self.cli(exc=requests.ConnectionError("refused"))
        with self.assertRaises(EC.EVoiceDown):
            c.health()
        c, _ = self.cli(exc=requests.Timeout("slow"))
        with self.assertRaises(EC.EVoiceDown) as cm:
            c.health()
        self.assertTrue(cm.exception.timeout)

    def test_http_error_detail(self):
        c, _ = self.cli(FakeResp(429, {"detail": "Hàng đợi đầy"}))
        with self.assertRaises(EC.EVoiceHttpError) as cm:
            c.create_job({})
        self.assertEqual((cm.exception.status, cm.exception.detail), (429, "Hàng đợi đầy"))
        c, _ = self.cli(FakeResp(401, None, text="<html>login</html>"))
        with self.assertRaises(EC.EVoiceHttpError) as cm:
            c.health()
        self.assertEqual(cm.exception.detail, "HTTP 401", "khong lo HTML ra trang")
        c, _ = self.cli(FakeResp(302, None, text=""))
        with self.assertRaises(EC.EVoiceHttpError):
            c.health()

    def test_non_json_is_down(self):
        c, _ = self.cli(FakeResp(200, None, text="<html>captive portal</html>"))
        with self.assertRaises(EC.EVoiceDown):
            c.health()

    def test_path_injection_blocked(self):
        c, s = self.cli(FakeResp(200, {}))
        for bad in ("../health", "a/b", "a?x=1", "", None, "a#b", "..", ".", "ạ"):
            with self.assertRaises(EC.EVoiceHttpError):
                c.get_job(bad)
        self.assertEqual(s.calls, [])

    def test_audio_stream(self):
        c, _ = self.cli(FakeResp(200, None, headers={"Content-Type": "audio/mpeg; x=1"}, chunks=[b"ab", b"cd"]))
        self.assertEqual(c.job_audio("j1"), (b"abcd", "audio/mpeg"))
        r = FakeResp(200, None, chunks=[b"a", OSError("reset")])
        c, _ = self.cli(r)
        with self.assertRaises(EC.EVoiceDown):
            c.job_audio("j1")
        self.assertTrue(r.closed)
        c, _ = self.cli(FakeResp(200, None, chunks=[b"x" * (30 * 1024 * 1024 + 1)]))
        with self.assertRaises(EC.EVoiceHttpError):
            c.voice_sample("v1")

    def test_lists(self):
        c, _ = self.cli(FakeResp(200, {"voices": [{"id": "v"}]}))
        self.assertEqual(c.voices(), [{"id": "v"}])
        c, _ = self.cli(FakeResp(200, {}))
        self.assertEqual(c.brands(), [])


if __name__ == "__main__":
    unittest.main()
