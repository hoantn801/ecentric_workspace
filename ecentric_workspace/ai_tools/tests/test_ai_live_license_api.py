# Copyright (c) 2026, eCentric and contributors
"""Ban quyen AI Live - lop API khach (controllers/license_api.py + infrastructure/license_guard.py) voi `frappe` gia:
429 khi qua tan suat, body > 32 KB, loi bat ky -> request "pending" / checkin "ok" (khong bao gio blocked, khong lo payload).
    python -m unittest ecentric_workspace.ai_tools.tests.test_ai_live_license_api"""
import importlib
import json
import sys
import types
import unittest
from unittest import mock


GUARD = "ecentric_workspace.ai_tools.features.ai_live.infrastructure.license_guard"
API = "ecentric_workspace.ai_tools.features.ai_live.controllers.license_api"


class Cache:
    def __init__(self):
        self.v, self.ttl = {}, {}

    def make_key(self, k):
        return "site|" + k

    def incrby(self, k, n):
        self.v[k] = self.v.get(k, 0) + n
        return self.v[k]

    def expire(self, k, s):
        self.ttl[k] = s


def fake_frappe(body=b"", length=None):
    f = types.ModuleType("frappe")
    f.local = types.SimpleNamespace(response={}, request_ip="5.5.5.5")
    f.log = {"commit": 0, "rollback": 0, "errors": []}
    f.db = types.SimpleNamespace(commit=lambda: f.log.__setitem__("commit", f.log["commit"] + 1),
                                 rollback=lambda: f.log.__setitem__("rollback", f.log["rollback"] + 1))
    f.log_error = lambda title=None, **kw: f.log["errors"].append(title)
    f.whitelist = lambda **kw: (lambda fn: fn)
    f.request = types.SimpleNamespace(content_length=len(body) if length is None else length,
                                      get_data=lambda cache=True: body)
    f._cache = Cache()
    f.cache = lambda: f._cache
    return f


class Svc:
    seen, boom = [], None

    def execute(self, body, ip):
        Svc.seen.append((body, ip))
        if Svc.boom:
            raise Svc.boom
        return {"status": "issued", "token": "T"}


class TestLicenseApi(unittest.TestCase):
    def load(self, f):
        """Nap moi 2 module voi frappe gia (test khac trong bo co the da thay / xoa sys.modules)."""
        with mock.patch.dict(sys.modules, {"frappe": f}):
            for n in (GUARD, API):
                sys.modules.pop(n, None)
            importlib.import_module(GUARD)
            return importlib.import_module(API), f

    def setUp(self):
        Svc.seen, Svc.boom = [], None

    def test_ok_envelope_and_commit(self):
        api, f = self.load(fake_frappe(json.dumps({"product": "elive"}).encode()))
        with mock.patch.dict(sys.modules, {"frappe": f}):
            out = api._serve("request", 30, Svc)
        self.assertEqual(out, {"success": True, "message": "", "data": {"status": "issued", "token": "T"}})
        self.assertEqual(Svc.seen, [({"product": "elive"}, "5.5.5.5")])
        self.assertEqual(f.log["commit"], 1)

    def test_rate_limit_429_per_ip(self):
        api, f = self.load(fake_frappe(b"{}"))
        with mock.patch.dict(sys.modules, {"frappe": f}):
            outs = [api._serve("checkin", 3, Svc) for _ in range(4)]
        self.assertEqual([o["success"] for o in outs], [True, True, True, False])
        self.assertEqual(f.local.response["http_status_code"], 429)
        self.assertEqual(len(Svc.seen), 3)

    def test_errors_are_safe_and_do_not_log_payload(self):
        api, f = self.load(fake_frappe(b'{"product": "elive", "secret": "zzz"}'))
        Svc.boom = RuntimeError("zzz")
        with mock.patch.dict(sys.modules, {"frappe": f}):
            r = api._serve("request", 30, Svc)
            c = api._serve("checkin", 60, Svc)
        self.assertEqual(r["data"]["status"], "pending")
        self.assertEqual(c["data"], {"status": "ok"})
        self.assertEqual(f.log["rollback"], 2)
        self.assertNotIn("zzz", json.dumps(f.log["errors"]))

    def test_body_over_32kb_is_none(self):
        api, f = self.load(fake_frappe(b"{" + b" " * 40000 + b"}"))
        with mock.patch.dict(sys.modules, {"frappe": f}):
            api._serve("request", 30, Svc)
        self.assertEqual(Svc.seen[0][0], None)
        api, f = self.load(fake_frappe(b"not json"))
        with mock.patch.dict(sys.modules, {"frappe": f}):
            api._serve("request", 30, Svc)
        self.assertEqual(Svc.seen[1][0], None)


if __name__ == "__main__":
    unittest.main()
