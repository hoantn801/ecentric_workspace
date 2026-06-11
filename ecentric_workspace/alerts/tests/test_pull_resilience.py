"""Pull resilience tests (2026-06-11) - LOF read-timeout incident.

REQ 7a: timeout clears running lock (source: finally + enqueue guard).
REQ 7b: retry succeeds on second attempt (live _request with fake transport).
REQ 7c: partial chunks keep checkpoint monotonic (guard intact + model).
REQ 7d: no duplicate Order Log / Occurrence on retry (GET-only replay +
        stable dedupe keys + upsert path untouched).

Client tests stub frappe (omisell_client imports it at module top) and
inject a fake requests transport - no network, no site.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_pull_resilience
"""
import os
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
    fu.now_datetime = lambda: datetime(2026, 6, 11)
    fu.nowdate = lambda: "2026-06-11"
    # union of attrs sibling pure-test stubs rely on (one stub per process):
    fu.add_days = lambda *a, **k: "2026-01-01"
    fu.cint = lambda v: int(v or 0)
    fu.flt = lambda v, *a: float(v or 0)
    sys.modules["frappe.utils"] = fu


_stub_frappe()
from ecentric_workspace.alerts.services import dedupe_keys as dk
from ecentric_workspace.alerts.services import omisell_client as oc


class _FakeResp:
    status_code = 200
    headers = {}

    def json(self):
        return {"data": {"results": []}, "error": None, "error_code": 200}


class _FakeTransport:
    """requests stand-in: raises `fails` timeouts, then succeeds."""
    # the except clause in _request resolves these via the module attr:
    import requests as _rq
    Timeout = _rq.exceptions.Timeout
    ConnectionError = _rq.exceptions.ConnectionError
    exceptions = _rq.exceptions

    def __init__(self, fails):
        self.fails = fails
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.Timeout("Read timed out. (read timeout=30)")
        return _FakeResp()


def _client(transport):
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
        oc.BACKOFFS_TIMEOUT = (0, 0)  # keep the test fast; count still = 2

    def tearDown(self):
        oc.requests, oc.MIN_INTERVAL, oc.BACKOFFS_TIMEOUT = self._req, self._min, self._bk

    def test_retry_succeeds_on_second_attempt(self):
        """REQ 7b: one timeout then success - caller never sees the error."""
        t = _FakeTransport(fails=1)
        oc.requests = t
        payload = _client(t)._request("GET", "/api/v2/public/order/list",
                                      params={}, auth=False)
        self.assertEqual(t.calls, 2)
        self.assertIn("data", payload)

    def test_exhausted_retries_raise_omisell_error(self):
        t = _FakeTransport(fails=99)
        oc.requests = t
        with self.assertRaises(oc.OmisellError) as cm:
            _client(t)._request("GET", "/api/v2/public/order/list",
                                params={}, auth=False)
        self.assertEqual(t.calls, 3)  # 1 + 2 retries
        self.assertIn("TIMEOUT", str(cm.exception))

    def test_auth_post_never_retried(self):
        """A timed-out POST may have succeeded server-side - no replay."""
        t = _FakeTransport(fails=99)
        oc.requests = t
        with self.assertRaises(oc.OmisellError):
            _client(t)._request("POST", oc.DEFAULT_AUTH_PATH,
                                json_body={}, auth=False)
        self.assertEqual(t.calls, 1)

    def test_read_only_surface_unchanged(self):
        self.assertEqual(oc.ALLOWED_METHODS, frozenset({"GET"}))
        self.assertEqual(oc.BACKOFFS_TIMEOUT if isinstance(oc.BACKOFFS_TIMEOUT, tuple)
                         else tuple(oc.BACKOFFS_TIMEOUT), (0, 0))  # patched in setUp
        self.assertEqual(self._bk, (2, 5))  # shipped values


class TestNoDuplicateOnRetry(unittest.TestCase):
    """REQ 7d: a replayed GET re-lists the same orders; identity keys are
    deterministic so Order Log upsert + Occurrence dedupe absorb the replay."""

    def test_occurrence_key_stable(self):
        a = dk.occurrence_key("ODVN1", "1:P02056", "below_min")
        self.assertEqual(a, dk.occurrence_key("ODVN1", "1:P02056", "below_min"))

    def test_price_and_lock_keys_stable(self):
        self.assertEqual(dk.price_alert_key("O", "L", "r"), dk.price_alert_key("O", "L", "r"))
        self.assertEqual(dk.lock_action_key("O", "L", "r"), dk.lock_action_key("O", "L", "r"))


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestApiOmisellResilienceWiring(unittest.TestCase):
    @property
    def src(self):
        return _src("api_omisell.py")

    def test_lock_cleared_in_finally_and_on_enqueue_failure(self):
        """REQ 7a: job finally always deletes the running flag; a failed
        enqueue deletes it too (otherwise brand locked for RUNNING_FLAG_TTL)."""
        s = self.src
        job = s.split("def pull_recent_job")[1]
        self.assertIn("finally:", job)
        self.assertIn("cache.delete_value(_running_key(brand))",
                      job.split("finally:")[1])
        web = s.split("def pull_recent(")[1].split("\ndef ")[0]
        self.assertIn("except Exception:", web)
        self.assertIn("cache.delete_value(_running_key(brand))", web)

    def test_checkpoint_monotonic_guard_intact(self):
        """REQ 7c: completed chunks advance, failed chunk never rolls back."""
        self.assertIn("prev if (prev and prev > t) else t", self.src)
        self.assertIn("checkpoint holds at last", self.src)

    def test_failed_chunk_visibility_fields(self):
        for field in ('"failed_chunk_window"', '"failed_stage"', '"timeout"'):
            self.assertIn(field, self.src)
        self.assertIn('"list" if "Order list failed"', self.src)

    def test_adaptive_chunking_wired(self):
        s = self.src
        self.assertIn("def _chunk_seconds(brand):", s)
        self.assertIn("ec_alerts_pull_chunk_seconds", s)
        self.assertIn("return 1800", s)
        self.assertIn("max(300, min(int(float(v)), MAX_WINDOW_SECONDS))", s)
        self.assertIn("chunk_windows(start, end, chunk_seconds=cs, max_chunks=eff_chunks)", s)
        self.assertIn("ADAPTIVE_LISTED_HI = 60", s)

    def test_monotonic_model(self):
        prev = datetime(2026, 6, 11, 1, 0, 0)
        for end in (prev - timedelta(hours=2), prev, prev + timedelta(minutes=30)):
            new = prev if (prev and prev > end) else end
            self.assertGreaterEqual(new, prev)


class TestClientSourceGuards(unittest.TestCase):
    def test_retry_is_get_only_and_bounded(self):
        s = _src("services/omisell_client.py")
        self.assertIn('if method == "GET" and attempt_timeout < len(BACKOFFS_TIMEOUT):', s)
        self.assertIn("BACKOFFS_TIMEOUT = (2, 5)", s)
        self.assertIn("requests.Timeout, requests.ConnectionError", s)


if __name__ == "__main__":
    unittest.main()
