# Copyright (c) 2026, eCentric and contributors
"""Giong doc AI: lop API (controllers/api.py) + job nen voi `frappe` gia - envelope, 403, rollback,
file nhi phan, callback Guest (chu ky / commit / 500), kill switch.
    python -m unittest ecentric_workspace.ai_tools.tests.test_ai_voice_api"""
import importlib
import json
import sys
import types
import unittest


class _ValidationError(Exception):
    pass


def _fake_frappe():
    f = types.ModuleType("frappe")
    f.ValidationError = _ValidationError
    f.local = types.SimpleNamespace(response={})
    f.session = types.SimpleNamespace(user="u@x")
    f.conf = {}
    f.log = {"commit": 0, "rollback": 0, "errors": []}
    f.db = types.SimpleNamespace(commit=lambda: f.log.__setitem__("commit", f.log["commit"] + 1),
                                 rollback=lambda: f.log.__setitem__("rollback", f.log["rollback"] + 1))
    f.utils = types.SimpleNamespace(strip_html=lambda s: s.replace("<b>", "").replace("</b>", ""))
    f.roles = ["EC AI Voice User"]
    f.get_roles = lambda user=None: list(f.roles)
    f.log_error = lambda title=None, **kw: f.log["errors"].append(title)
    f.whitelist = lambda **kw: (lambda fn: fn)
    f.get_module = lambda n: sys.modules.get(n) or importlib.import_module(n)
    f.request = types.SimpleNamespace(get_data=lambda cache=True: f.raw)
    f.raw = b""
    f.headers = {}
    f.get_request_header = lambda k: f.headers.get(k)
    f.logger = lambda name=None: types.SimpleNamespace(info=lambda *a, **k: None)
    return f


def _load_modules():
    """Nap 1 lan luc thu thap test (goi that con nguyen) - test khac trong bo co the thay sys.modules
    ["ecentric_workspace"] bang module gia o muc module, nen KHONG import lai trong setUp."""
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = _fake_frappe()
    try:
        from ecentric_workspace.ai_tools.features.ai_voice.controllers import api
        from ecentric_workspace.ai_tools.features.ai_voice.jobs import _common, poll_jobs_job, submit_job_job
        from ecentric_workspace.ai_tools.features.ai_voice.application import (  # noqa: F401 - nap san cho patch()
            _deps, audio_service, create_job_service, handle_callback_service, poll_jobs_service, sync_voices_service)
    finally:
        if saved is not None:
            sys.modules["frappe"] = saved
        else:
            sys.modules.pop("frappe", None)
    snap = {k: v for k, v in sys.modules.items() if k == "ecentric_workspace" or k.startswith("ecentric_workspace.")}
    return api, (api, _common, poll_jobs_job, submit_job_job), snap


API, FRAPPE_USERS, PKG_SNAPSHOT = _load_modules()


class Base(unittest.TestCase):
    def setUp(self):
        # Test khac trong bo thay / xoa sys.modules["ecentric_workspace*"] -> dung lai ban that da chup, tra lai sau.
        self._pkg = {k: v for k, v in sys.modules.items() if k == "ecentric_workspace" or k.startswith("ecentric_workspace.")}
        for k in list(self._pkg):
            del sys.modules[k]
        sys.modules.update(PKG_SNAPSHOT)
        self._saved = sys.modules.get("frappe")
        self.f = _fake_frappe()
        sys.modules["frappe"] = self.f
        for m in FRAPPE_USERS:
            m.frappe = self.f
        self.api = API

    def tearDown(self):
        if self._saved is not None:
            sys.modules["frappe"] = self._saved
        else:
            sys.modules.pop("frappe", None)
        for k in [k for k in sys.modules if k == "ecentric_workspace" or k.startswith("ecentric_workspace.")]:
            del sys.modules[k]
        sys.modules.update(self._pkg)

    def patch(self, module, cls, obj):
        mod = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.application." + module]
        old = getattr(mod, cls)
        setattr(mod, cls, obj)
        self.addCleanup(setattr, mod, cls, old)


class TestEnvelope(Base):
    def test_success_error_permission_crash(self):
        C = self.api.C
        out = self.api._run(lambda: {"a": 1})
        self.assertEqual(out, {"success": True, "message": "", "data": {"a": 1}})

        def boom(exc):
            def fn():
                raise exc
            return fn
        out = self.api._run(boom(C.AiVoiceError("Thiếu nội dung")))
        self.assertEqual((out["success"], out["message"]), (False, "Thiếu nội dung"))
        out = self.api._run(boom(C.AiVoicePermission("Không có quyền")))
        self.assertEqual(self.f.local.response["http_status_code"], 403)
        out = self.api._run(boom(_ValidationError("<b>Link sai</b>")))
        self.assertEqual(out["message"], "Link sai")
        out = self.api._run(boom(KeyError("secret internals")))
        self.assertEqual(out["message"], C.Msg.UNKNOWN, "khong lo loi noi bo")
        self.assertEqual(self.f.log["errors"], ["ai_voice api"])
        self.assertEqual(self.f.log["rollback"], 4)

    def test_payload_parsing(self):
        self.assertEqual(self.api._payload('{"text": "a"}'), {"text": "a"})
        self.assertEqual(self.api._payload({"x": 1}), {"x": 1})
        self.assertEqual(self.api._payload("[1]"), {})
        self.assertEqual(self.api._payload(None), {})
        with self.assertRaises(self.api.C.AiVoiceError):
            self.api._payload("{bad")

    def test_create_job_passes_user_roles(self):
        seen = {}

        class Fake:
            def execute(self, user, roles, payload):
                seen.update(user=user, roles=roles, payload=payload)
                return {"name": "J1"}
        self.patch("create_job_service", "CreateJobService", Fake)
        out = self.api.create_job(data=json.dumps({"text": "chào"}))
        self.assertTrue(out["success"])
        self.assertEqual(seen, {"user": "u@x", "roles": ["EC AI Voice User"], "payload": {"text": "chào"}})


class TestFiles(Base):
    def test_download_inline_and_attachment(self):
        class Fake:
            def job_audio(self, user, roles, name):
                return ("bai.mp3", b"ID3", "audio/mpeg")
        self.patch("audio_service", "AudioService", Fake)
        self.assertIsNone(self.api.download_audio(name="J1"))
        r = self.f.local.response
        self.assertEqual((r["type"], r["filecontent"], r["content_type"], r["display_content_as"]),
                         ("download", b"ID3", "audio/mpeg", "inline"))
        self.api.download_audio(name="J1", dl=1)
        self.assertEqual(self.f.local.response["display_content_as"], "attachment")

    def test_download_error_is_json(self):
        C = self.api.C

        class Fake:
            def job_audio(self, user, roles, name):
                raise C.AiVoicePermission(C.Msg.NOT_YOURS)
        self.patch("audio_service", "AudioService", Fake)
        out = self.api.download_audio(name="J1")
        self.assertEqual((out["success"], self.f.local.response.get("type")), (False, None))
        self.assertEqual(self.f.local.response["http_status_code"], 403)

    def test_sample_commits_cache(self):
        class Fake:
            def sample(self, user, roles, name):
                return ("mau.wav", b"RIFF", "audio/wav")
        self.patch("audio_service", "AudioService", Fake)
        self.api.voice_sample(name="P1")
        self.assertEqual(self.f.log["commit"], 1, "GET khong tu commit - phai commit ban cache mau")


class TestCallback(Base):
    def test_good_bad_crash(self):
        H = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.application.handle_callback_service"]
        calls = []

        class Fake:
            def execute(self, raw, sig):
                calls.append((raw, sig))
                if sig == "bad":
                    raise H.BadSignature()
                if sig == "boom":
                    raise RuntimeError("db down")
                return "ok"
        self.patch("handle_callback_service", "HandleCallbackService", Fake)
        self.f.raw, self.f.headers = b'{"id":"r1"}', {"X-eVoice-Signature": "abc"}
        self.assertEqual(self.api.evoice_callback(), {"ok": True, "result": "ok"})
        self.assertEqual(calls[-1], (b'{"id":"r1"}', "abc"), "kiem chu ky tren body THO")
        self.assertEqual(self.f.log["commit"], 1)
        self.f.headers = {"X-eVoice-Signature": "bad"}
        self.assertEqual(self.api.evoice_callback(), {"ok": False})
        self.assertEqual(self.f.local.response["http_status_code"], 403)
        self.f.headers = {"X-eVoice-Signature": "boom"}
        self.api.evoice_callback()
        self.assertEqual(self.f.local.response["http_status_code"], 500, "500 -> eVoice khong coi la da bao; poll van cuu")
        self.assertEqual(self.f.log["errors"], ["ai_voice callback"])
        self.f.headers = {}
        self.api.evoice_callback()
        self.assertEqual(calls[-1][1], "", "khong co header -> chuoi rong (service tu choi)")

    def test_unknown_job_asks_retry(self):
        class Fake:
            def execute(self, raw, sig):
                return "unknown"
        self.patch("handle_callback_service", "HandleCallbackService", Fake)
        out = self.api.evoice_callback()
        self.assertEqual((out["ok"], self.f.local.response["http_status_code"]), (False, 404),
                         "phieu chua commit -> 404 de eVoice gui lai")


class TestKillSwitchAndNames(Base):
    def test_client_factory_paused(self):
        _deps = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.application._deps"]

        class S:
            def get(self, with_token=False):
                return {"token": "t", "base_url": "https://v.x", "timeout": 30}
        self.f.conf["ec_ai_voice_disabled"] = 1
        with self.assertRaises(self.api.C.AiVoiceError) as cm:
            _deps.client_factory(S())()
        self.assertEqual(str(cm.exception), self.api.C.Msg.PAUSED)
        self.f.conf.clear()
        self.assertEqual(_deps.client_factory(S())().base, "https://v.x")

    def test_download_name_ascii(self):
        _safe_name = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.application.audio_service"]._safe_name
        self.assertEqual(_safe_name("Kịch bản Đồng Tháp / số 1"), "Kich_ban_Dong_Thap___so_1")
        self.assertEqual(_safe_name("???"), "___")
        self.assertEqual(_safe_name(""), "giong_doc")


class TestJobs(Base):
    def test_kill_switch_and_guard(self):
        _common = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.jobs._common"]
        submit_job_job = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.jobs.submit_job_job"]
        self.f.conf["ec_ai_voice_disabled"] = 1
        self.assertIsNone(submit_job_job.run(name="J1"))
        self.f.conf.clear()
        self.assertEqual(_common.guarded("x", lambda: 5), 5)
        self.assertEqual(self.f.log["commit"], 1)

        def boom():
            raise RuntimeError("x")
        self.assertIsNone(_common.guarded("x", boom))
        self.assertEqual((self.f.log["rollback"], self.f.log["errors"]), (1, ["ai_voice x"]))

    def test_poll_one_bad_job_does_not_stop_batch(self):
        poll_jobs_job = sys.modules["ecentric_workspace.ai_tools.features.ai_voice.jobs.poll_jobs_job"]
        done = []

        class FakePoll:
            def targets(self):
                return ["J1", "J2", "J3"]

            def process(self, n):
                if n == "J2":
                    raise RuntimeError("bad row")
                done.append(n)
                return "ok"

        class FakeSync:
            def reconcile(self):
                return 0
        self.patch("poll_jobs_service", "PollJobsService", FakePoll)
        self.patch("sync_voices_service", "SyncVoicesService", FakeSync)
        poll_jobs_job.run()
        self.assertEqual(done, ["J1", "J3"])
        self.assertEqual(self.f.log["rollback"], 1)
        self.assertEqual(self.f.log["commit"], 3)


if __name__ == "__main__":
    unittest.main()
