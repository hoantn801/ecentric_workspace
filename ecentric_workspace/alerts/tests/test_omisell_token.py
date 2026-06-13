"""Hotfix A token tests (2026-06-13). Stubbed frappe + fake requests transport
+ fake BIS doc; no DB, no network. Proves token reuse, fallback TTL, bounded
auth retry, no-retry on 401, and that no token/credential is ever logged.

    bench run-tests --module ecentric_workspace.alerts.tests.test_omisell_token
"""
import sys
import types
import unittest
from datetime import datetime, timedelta


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.ValidationError = type("ValidationError", (Exception,), {})
    f._ = lambda s: s
    f._logs = []          # captured logger.info payloads
    f._errs = []
    f.conf = types.SimpleNamespace(get=lambda *a, **k: None)
    f.logger = lambda *a, **k: types.SimpleNamespace(
        info=lambda payload: f._logs.append(payload))
    f.log_error = lambda *a, **k: f._errs.append(a)
    f.get_traceback = lambda *a, **k: "tb"
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: datetime(2026, 6, 13, 12, 0, 0)
    fu.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    fu.add_to_date = lambda d, minutes=0, **k: d + timedelta(minutes=minutes)
    sys.modules["frappe.utils"] = fu


_stub_frappe()
from ecentric_workspace.alerts.services import omisell_client as oc

SECRET_TOKEN = "SUPER-SECRET-TOKEN-xyz"
API_KEY = "KEY-123"
API_SECRET = "SECRET-456"


class TimestampMismatchError(Exception):
    """Stand-in matching the class-name check in _persist_token."""


class FakeBis:
    def __init__(self, token=None, exp=None, last_sync_at="CHECKPOINT", fail_saves=0):
        self.name = "BIS-LOF"
        self.base_url = "https://api.test"
        self.token = token
        self.token_expired_at = exp
        self.last_sync_at = last_sync_at        # must NOT be touched by token persist
        self._pw = {"api_key": API_KEY, "api_secret": API_SECRET, "token": token}
        self.saved = 0
        self.reloads = 0
        self._fail_saves = fail_saves           # raise TimestampMismatch on first N saves

    def get_password(self, field, raise_exception=False):
        return self._pw.get(field)

    def reload(self):
        self.reloads += 1

    def save(self, ignore_permissions=False):
        if self._fail_saves > 0:
            self._fail_saves -= 1
            raise TimestampMismatchError("modified mismatch")
        self._pw["token"] = self.token
        self.saved += 1


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.headers = {}
        self._body = body if body is not None else {"data": {"token": SECRET_TOKEN}}

    def json(self):
        return self._body


class FakeTransport:
    """Scripted responses for the auth POST. Each item: 'timeout', int status,
    or a _Resp. Records call count."""
    import requests as _rq
    Timeout = _rq.exceptions.Timeout
    ConnectionError = _rq.exceptions.ConnectionError
    exceptions = _rq.exceptions

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls += 1
        item = self.script.pop(0) if self.script else _Resp()
        if item == "timeout":
            raise self.Timeout("read timed out")
        if isinstance(item, int):
            return _Resp(status=item, body={"messages": "err"})
        return item


def _client(bis):
    c = oc.OmisellClient.__new__(oc.OmisellClient)
    c.bis = bis
    c.base = bis.base_url
    c.last_rate_header = None
    c._last_call = 0.0
    return c


class _Base(unittest.TestCase):
    def setUp(self):
        import frappe
        frappe._logs = []
        frappe._errs = []
        self._min, self._ab = oc.MIN_INTERVAL, oc.AUTH_BACKOFFS
        oc.MIN_INTERVAL = 0
        oc.AUTH_BACKOFFS = (0, 0)
        self._req = oc.requests

    def tearDown(self):
        oc.MIN_INTERVAL, oc.AUTH_BACKOFFS, oc.requests = self._min, self._ab, self._req


class TestToken(_Base):
    def test_01_valid_cached_token_avoids_auth_post(self):
        bis = FakeBis(token=SECRET_TOKEN, exp=datetime(2026, 6, 13, 13, 0, 0))  # +1h
        t = FakeTransport([])
        oc.requests = t
        self.assertEqual(_client(bis)._ensure_token(), SECRET_TOKEN)
        self.assertEqual(t.calls, 0)                       # no auth POST
        import frappe
        self.assertTrue(any(l.get("omisell_token_source") == "reused_cached"
                            for l in frappe._logs))

    def test_02_missing_expired_time_sets_fallback_ttl(self):
        bis = FakeBis(token=None, exp=None)
        oc.requests = FakeTransport([_Resp(body={"data": {"token": SECRET_TOKEN}})])  # no expired_time
        c = _client(bis)
        self.assertEqual(c._ensure_token(), SECRET_TOKEN)
        # fallback: now + 30 min
        self.assertEqual(bis.token_expired_at, datetime(2026, 6, 13, 12, 30, 0))
        import frappe
        self.assertTrue(any(l.get("omisell_token_source") == "fallback_ttl_applied"
                            for l in frappe._logs))

    def test_03_subsequent_request_reuses_fallback_token(self):
        bis = FakeBis(token=None, exp=None)
        oc.requests = FakeTransport([_Resp(body={"data": {"token": SECRET_TOKEN}})])
        c = _client(bis)
        c._ensure_token()                                   # 1st: auth + fallback ttl
        t2 = FakeTransport([])
        oc.requests = t2
        self.assertEqual(c._ensure_token(), SECRET_TOKEN)   # 2nd: reuse
        self.assertEqual(t2.calls, 0)

    def test_04_auth_timeout_retries_then_succeeds(self):
        bis = FakeBis()
        t = FakeTransport(["timeout", _Resp()])
        oc.requests = t
        self.assertEqual(_client(bis)._authenticate(), SECRET_TOKEN)
        self.assertEqual(t.calls, 2)                        # 1 timeout + 1 success

    def test_05_auth_5xx_retries_then_succeeds(self):
        bis = FakeBis()
        t = FakeTransport([503, _Resp()])
        oc.requests = t
        self.assertEqual(_client(bis)._authenticate(), SECRET_TOKEN)
        self.assertEqual(t.calls, 2)

    def test_06_auth_401_does_not_retry(self):
        bis = FakeBis()
        t = FakeTransport([401, _Resp()])
        oc.requests = t
        with self.assertRaises(oc.OmisellAuthError):
            _client(bis)._authenticate()
        self.assertEqual(t.calls, 1)                        # NOT retried

    def test_400_does_not_retry(self):
        bis = FakeBis()
        t = FakeTransport([400, _Resp()])
        oc.requests = t
        with self.assertRaises(oc.OmisellError):
            _client(bis)._authenticate()
        self.assertEqual(t.calls, 1)

    def test_auth_timeout_exhausts_at_3_attempts(self):
        bis = FakeBis()
        t = FakeTransport(["timeout", "timeout", "timeout", "timeout"])
        oc.requests = t
        with self.assertRaises(oc.OmisellError):
            _client(bis)._authenticate()
        self.assertEqual(t.calls, 3)                        # 3 total (1 + 2 retries)

    def test_07_token_and_credentials_never_logged(self):
        bis = FakeBis()
        oc.requests = FakeTransport([_Resp()])
        _client(bis)._authenticate()
        import frappe
        blob = repr(frappe._logs) + repr(frappe._errs)
        self.assertNotIn(SECRET_TOKEN, blob)
        self.assertNotIn(API_KEY, blob)
        self.assertNotIn(API_SECRET, blob)


class TestTokenPersistence(_Base):
    """Production hotfix 2026-06-14: token refresh must reload-before-save (no
    stale-doc TimestampMismatch race with the checkpoint), never touch
    last_sync_at, and retry at most once."""

    def test_reload_before_save(self):
        bis = FakeBis()
        oc.requests = FakeTransport([_Resp()])
        _client(bis)._authenticate()
        self.assertEqual(bis.reloads, 1)            # reloaded before the save
        self.assertEqual(bis.saved, 1)
        self.assertEqual(bis._pw["token"], SECRET_TOKEN)

    def test_token_persist_does_not_touch_checkpoint(self):
        bis = FakeBis(last_sync_at="CHECKPOINT")
        oc.requests = FakeTransport([_Resp()])
        _client(bis)._authenticate()
        self.assertEqual(bis.last_sync_at, "CHECKPOINT")   # checkpoint untouched

    def test_one_retry_on_timestamp_mismatch(self):
        bis = FakeBis(fail_saves=1)                  # first save raises, retry succeeds
        oc.requests = FakeTransport([_Resp()])
        _client(bis)._authenticate()
        self.assertEqual(bis.reloads, 2)            # reloaded again on the retry
        self.assertEqual(bis.saved, 1)              # succeeded on the 2nd attempt
        self.assertEqual(bis._pw["token"], SECRET_TOKEN)

    def test_no_blind_retry_second_mismatch_raises(self):
        bis = FakeBis(fail_saves=2)                  # both attempts mismatch
        oc.requests = FakeTransport([_Resp()])
        with self.assertRaises(TimestampMismatchError):
            _client(bis)._authenticate()
        self.assertEqual(bis.reloads, 2)            # exactly 2 attempts, no more


if __name__ == "__main__":
    unittest.main()
