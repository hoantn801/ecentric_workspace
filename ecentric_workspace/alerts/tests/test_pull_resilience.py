"""Minimal pull-resilience hotfix tests (2026-06-12, LOF read-timeout).

Scope of the hotfix (and of these tests):
  1. GET-only bounded timeout retry (2s, 5s; max 2 after first failure).
  2. Read timeout default 60s, site_config ec_alerts_omisell_read_timeout
     (clamped 10..180).
  3. Running lock always cleared (job finally + enqueue-failure guard).
  4. 1-hour chunk planning UNCHANGED - the reverted adaptive/catch-up logic
     (PR #25/#26) must NOT sneak back in.
  5. last_run visibility: failed_stage / failed_chunk_window / timeout.

Client tests stub frappe and inject a fake transport - no network, no site.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_pull_resilience
"""
import os
import sys
import types
import unittest
from datetime import datetime


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.ValidationError = type("ValidationError", (Exception,), {})
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f._ = lambda s: s
    f.conf = types.SimpleNamespace(get=lambda *a, **k: None)
    f.throw = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
    f.log_error = lambda *a, **k: None
    f.session = types.SimpleNamespace(user="Administrator")
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.add_to_date = lambda d, **k: d
    fu.get_datetime = lambda v: v
    fu.now_datetime = lambda: datetime(2026, 6, 12)
    fu.nowdate = lambda: "2026-06-12"
    # union of attrs sibling pure-test stubs rely on (one stub per process):
    fu.add_days = lambda *a, **k: "2026-01-01"
    fu.cint = lambda v: int(v or 0)
    fu.flt = lambda v, *a: float(v or 0)
    sys.modules["frappe.utils"] = fu


_stub_frappe()
import frappe as _frappe_mod  # the stub (or real frappe on bench)
from ecentric_workspace.alerts.services import omisell_client as oc


class _FakeResp:
    status_code = 200
    headers = {}

    def json(self):
        return {"data": {"results": []}, "error": None, "error_code": 200}


class _FakeTransport:
    """requests stand-in: raises `fails` timeouts, then succeeds."""
    import requests as _rq
    Timeout = _rq.exceptions.Timeout
    ConnectionError = _rq.exceptions.ConnectionError
    exceptions = _rq.exceptions

    def __init__(self, fails):
        self.fails = fails
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1
        self.last_timeout_kwarg = k.get("timeout")
        if self.calls <= self.fails:
            raise self.Timeout("Read timed out. (read timeout=%s)" % k.get("timeout"))
        return _FakeResp()


def _client():
    c = oc.OmisellClient.__new__(oc.OmisellClient)
    c.base = "https://api.test"
    c.last_rate_header = None
    c._last_call = 0.0
    c.bis = None
    return c


class TestTimeoutRetry(unittest.TestCase):
    def setUp(self):
        self._req, self._min, self._bk = oc.requests, oc.MIN_INTERVAL, oc.BACKOFFS_TIMEOUT
        oc.MIN_INTERVAL = 0
        oc.BACKOFFS_TIMEOUT = (0, 0)  # keep tests fast; count still = 2

    def tearDown(self):
        oc.requests, oc.MIN_INTERVAL, oc.BACKOFFS_TIMEOUT = self._req, self._min, self._bk

    def test_retry_succeeds_on_second_attempt(self):
        """REQ 6a: one timeout then success - caller never sees the error."""
        t = _FakeTransport(fails=1)
        oc.requests = t
        payload = _client()._request("GET", "/api/v2/public/order/list",
                                     params={}, auth=False)
        self.assertEqual(t.calls, 2)
        self.assertIn("data", payload)

    def test_exhausted_retries_raise_clear_omisell_error(self):
        """REQ 6b: first failure + 2 retries = 3 calls, then OmisellError
        with TIMEOUT + the effective read_timeout in the message."""
        t = _FakeTransport(fails=99)
        oc.requests = t
        with self.assertRaises(oc.OmisellError) as cm:
            _client()._request("GET", "/api/v2/public/order/list",
                               params={}, auth=False)
        self.assertEqual(t.calls, 3)
        self.assertIn("TIMEOUT", str(cm.exception))
        self.assertIn("read_timeout=", str(cm.exception))

    def test_non_get_never_retried(self):
        """REQ 6d: a timed-out POST may have succeeded server-side."""
        t = _FakeTransport(fails=99)
        oc.requests = t
        with self.assertRaises(oc.OmisellError):
            _client()._request("POST", oc.DEFAULT_AUTH_PATH,
                               json_body={}, auth=False)
        self.assertEqual(t.calls, 1)

    def test_shipped_backoffs(self):
        self.assertEqual(self._bk, (2, 5))

    def test_read_only_surface_unchanged(self):
        self.assertEqual(oc.ALLOWED_METHODS, frozenset({"GET"}))


class TestReadTimeoutConfig(unittest.TestCase):
    def setUp(self):
        self._conf = _frappe_mod.conf

    def tearDown(self):
        _frappe_mod.conf = self._conf
        if hasattr(oc.frappe, "conf"):
            oc.frappe.conf = self._conf

    def _set(self, value):
        ns = types.SimpleNamespace(
            get=lambda k, *a: value if k == "ec_alerts_omisell_read_timeout" else None)
        oc.frappe.conf = ns

    def test_default_60(self):
        self._set(None)
        self.assertEqual(oc.read_timeout(), 60)
        self.assertEqual(oc.DEFAULT_READ_TIMEOUT, 60)

    def test_override_and_clamp(self):
        self._set(90)
        self.assertEqual(oc.read_timeout(), 90)
        self._set("120")
        self.assertEqual(oc.read_timeout(), 120)
        self._set(5)
        self.assertEqual(oc.read_timeout(), 10)    # floor
        self._set(9999)
        self.assertEqual(oc.read_timeout(), 180)   # ceiling
        self._set("garbage")
        self.assertEqual(oc.read_timeout(), 60)    # fail-safe

    def test_used_by_request(self):
        t = _FakeTransport(fails=0)
        old = oc.requests
        try:
            oc.requests, oc.MIN_INTERVAL = t, 0
            self._set(75)
            _client()._request("GET", "/x", auth=False)
            self.assertEqual(t.last_timeout_kwarg, 75)
        finally:
            oc.requests = old


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestApiOmisellWiring(unittest.TestCase):
    @property
    def src(self):
        return _src("api_omisell.py")

    def test_lock_cleared_in_finally_and_on_enqueue_failure(self):
        """REQ 6c: job finally always deletes the running flag; a failed
        enqueue deletes it too."""
        s = self.src
        job = s.split("def pull_recent_job")[1]
        self.assertIn("finally:", job)
        self.assertIn("cache.delete_value(_running_key(brand))",
                      job.split("finally:")[1])
        web = s.split("def pull_recent(")[1].split("\ndef ")[0]
        self.assertIn("except Exception:", web)
        self.assertIn("cache.delete_value(_running_key(brand))", web)

    def test_one_hour_planning_unchanged_no_adaptive(self):
        """REQ 4: the reverted PR #25/#26 logic must NOT return."""
        s = self.src
        self.assertIn("span_chunks = int((end - start).total_seconds() "
                      "// MAX_WINDOW_SECONDS) + 1", s)
        self.assertIn("chunk_windows(start, end, max_chunks=eff_chunks)", s)
        for banned in ("_chunk_seconds", "pull_planner", "MAX_CATCHUP",
                       "ADAPTIVE_", "done_partial", "chunk_seconds=cs"):
            self.assertNotIn(banned, s)

    def test_failed_chunk_visibility_fields(self):
        for field in ('"failed_chunk_window"', '"failed_stage"', '"timeout"'):
            self.assertIn(field, self.src)
        self.assertIn('"list" if "Order list failed"', self.src)

    def test_checkpoint_monotonic_guard_intact(self):
        self.assertIn("prev if (prev and prev > t) else t", self.src)


class TestClientSourceGuards(unittest.TestCase):
    def test_retry_get_only_bounded_and_timeout_configurable(self):
        s = _src("services/omisell_client.py")
        self.assertIn('if method == "GET" and attempt_timeout < len(BACKOFFS_TIMEOUT):', s)
        self.assertIn("BACKOFFS_TIMEOUT = (2, 5)", s)
        self.assertIn("requests.Timeout, requests.ConnectionError", s)
        self.assertIn("timeout=read_timeout()", s)
        self.assertIn("ec_alerts_omisell_read_timeout", s)


if __name__ == "__main__":
    unittest.main()
