"""Adaptive sub-window orchestrator tests (scalability mini-phase 2026-06-14).

Drives the REAL api_omisell.pull_window_adaptive with a fake Omisell client +
fake BIS, monkeypatching the service deps + config getters to deterministic
fakes (no DB writes, no network). Covers: under-cap, exactly-cap (no split),
over-cap split, multi-level split, boundary at mid-1/mid/mid+1 (no loss / no
dup), minimum-window-capped + alert dedupe, budget-exhausted-holds-at-left,
transient-queued-advances-checkpoint, retry-persistence-holds, probe no side
effect, stale-probe undercount, and the LOF 323-order regression.

    bench run-tests --module ecentric_workspace.alerts.tests.test_pull_adaptive

NOTE: in the OneDrive sandbox the api_omisell source read is truncated, so the
import is guarded - the suite skips there and runs on bench. The same logic is
additionally proven by an in-/tmp verbatim mirror during development.
"""
import unittest
from datetime import datetime, timedelta

from ecentric_workspace.alerts.services import subwindow_planner as swp

try:
    from ecentric_workspace.alerts import api_omisell as ao
    _IMPORT_OK = True
except Exception as _e:           # truncated mount / missing dep in sandbox
    ao = None
    _IMPORT_OK = False

H0 = datetime(2026, 6, 14, 0, 0, 0)


def E(dt):
    return int(dt.timestamp())


class FakeBis:
    def __init__(self, last_sync_at=None):
        self.name = "BIS"; self.last_sync_at = last_sync_at
        self.consecutive_failures = 0; self.credential_status = "Active"
    def reload(self):
        pass
    def save(self, ignore_permissions=False):
        pass


class FakeClient:
    def __init__(self, orders, fail_detail=None, raise_list=None, probe_override=None,
                 semantics="inclusive"):
        self.orders = orders
        self.detail_calls = []
        self.fail_detail = fail_detail or {}
        self.raise_list = raise_list
        self.probe_override = probe_override
        self.semantics = semantics        # remote backend: inclusive [from,to] or half_open [from,to)
    def _sel(self, f_ts, t_ts):
        if self.semantics == "half_open":
            return [n for (n, ut) in self.orders if f_ts <= ut < t_ts]
        return [n for (n, ut) in self.orders if f_ts <= ut <= t_ts]
    def get_orders(self, f_ts, t_ts, page=1, page_size=50):
        if self.raise_list:
            raise self.raise_list
        sel = self._sel(f_ts, t_ts)
        if page_size == 1:
            cnt = self.probe_override if self.probe_override is not None else len(sel)
            return {"data": {"count": cnt, "results": sel[:1], "next": len(sel) > 1}}
        return {"data": {"count": len(sel),
                         "results": [{"omisell_order_number": n} for n in sel],
                         "next": False}}
    def get_order_detail(self, number):
        self.detail_calls.append(number)
        if number in self.fail_detail:
            raise self.fail_detail[number]
        return {"data": {"_status_id": 1, "_status_name": "ok",
                         "external_order_id": number, "items": []}}


def spread(n, cf, ct, prefix="O"):
    span = E(ct) - E(cf)
    step = max(1, span // max(n, 1))
    return [("%s%d" % (prefix, i), E(cf) + min(i * step, span - 1)) for i in range(n)]


@unittest.skipUnless(_IMPORT_OK, "api_omisell import unavailable (sandbox mount truncation)")
class TestPullAdaptive(unittest.TestCase):
    def setUp(self):
        # deterministic fakes on the api_omisell module (no global pollution)
        self._saved = {k: getattr(ao, k) for k in (
            "_to_epoch", "ingestion", "order_retry", "action_queue", "norm",
            "brand_resolver", "_breaker_record", "_auth_failure",
            "_minimum_window_alert", "_ingestion_failure_alert",
            "_details_cap", "_min_subwindow_seconds", "_max_split_depth", "_skip_orders")}
        ao._to_epoch = lambda dt: int(dt.timestamp())
        ao.ingestion = type("I", (), {"ingest_orders": staticmethod(
            lambda batch: [{"status": "created"} for _ in batch])})
        ao.order_retry = type("R", (), {"upsert": staticmethod(lambda b, n, e: True)})
        ao.action_queue = type("A", (), {"process_pending_actions": staticmethod(lambda: {})})
        ao.norm = type("N", (), {
            "normalize_order_detail": staticmethod(lambda d: d),
            "is_real_sale": staticmethod(lambda sid, sname: (True, ""))})
        ao.brand_resolver = type("B", (), {"resolve_owner": staticmethod(lambda u, b: None)})
        self.breaker = []
        ao._breaker_record = lambda bis, success: self.breaker.append(success)
        ao._auth_failure = lambda bis, brand: setattr(bis, "credential_status", "Expired")
        self.min_alerts = []
        self._min_keys = set()
        def fake_min(brand, cf, ct, listed, cap):     # dedupe by brand+window+cap
            k = (brand, str(cf), str(ct), cap)
            if k in self._min_keys:
                return
            self._min_keys.add(k)
            self.min_alerts.append(k)
        ao._minimum_window_alert = fake_min
        self.fail_alerts = []
        ao._ingestion_failure_alert = lambda brand, msg, context=None: self.fail_alerts.append(str(msg))
        self._cap = [300]; self._min = [300]; self._depth = [6]
        ao._details_cap = lambda: self._cap[0]
        ao._min_subwindow_seconds = lambda: self._min[0]
        ao._max_split_depth = lambda: self._depth[0]
        ao._skip_orders = lambda: set()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(ao, k, v)

    def _run(self, brand, bis, client, cf, ct, budget=10 ** 9):
        tele = {"split_depth": 0, "subwindows_seen": 0, "subwindows_processed": 0,
                "checkpoint_advanced_to": None, "minimum_window_reached": False,
                "budget_exhausted": False, "stop_reason": None, "leaf_summaries": []}
        import time as _t
        deadline = _t.monotonic() + budget
        state = ao.pull_window_adaptive(brand, bis, client, cf, ct, deadline, 0, tele)
        return state, tele

    def test_under_cap_single_leaf(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(12, H0, ct)); bis = FakeBis()
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(t["split_depth"], 0)
        self.assertEqual(t["subwindows_processed"], 1)
        self.assertEqual(len(c.detail_calls), 12)

    def test_exactly_cap_no_split(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(300, H0, ct)); bis = FakeBis()
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(t["split_depth"], 0)
        self.assertEqual(len(c.detail_calls), 300)

    def test_over_cap_split_once(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(400, H0, ct)); bis = FakeBis()
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(t["split_depth"], 1)
        self.assertEqual(t["subwindows_processed"], 2)
        self.assertEqual(t["checkpoint_advanced_to"], str(ct))
        self.assertEqual(len(set(c.detail_calls)), 400)   # NO LOSS (seam may double-read)

    def test_multi_level_split(self):
        ct = H0 + timedelta(hours=1)
        self._cap[0] = 2
        # 8 orders offset 7s off every midpoint -> deterministic tiling (no seam
        # landing) so depth is identical under inclusive AND half-open backends.
        c = FakeClient([("O%d" % i, E(H0) + 7 + i * 450) for i in range(8)]); bis = FakeBis()
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(t["split_depth"], 2)
        self.assertEqual(t["subwindows_processed"], 4)
        self.assertEqual(len(set(c.detail_calls)), 8)

    def _boundary(self, semantics):
        ct = H0 + timedelta(hours=1); self._cap[0] = 2
        em = E(swp.split_point(H0, ct))
        c = FakeClient([("LEFT", em - 1), ("MID", em), ("RIGHT", em + 1)],
                       semantics=semantics)
        st, t = self._run("FES", FakeBis(), c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(set(c.detail_calls), {"LEFT", "MID", "RIGHT"})   # NO LOSS
        self.assertEqual(c.detail_calls.count("LEFT"), 1)                 # only seam may double
        self.assertEqual(c.detail_calls.count("RIGHT"), 1)
        return c

    def test_boundary_inclusive_backend(self):
        c = self._boundary("inclusive")
        self.assertEqual(c.detail_calls.count("MID"), 2)   # seam read by BOTH -> dedupe

    def test_boundary_half_open_backend(self):
        c = self._boundary("half_open")
        self.assertEqual(c.detail_calls.count("MID"), 1)   # clean tiling, no double

    def test_minimum_window_capped_and_dedupe(self):
        ct = H0 + timedelta(seconds=300); self._cap[0] = 2; self._min[0] = 300
        c = FakeClient(spread(10, H0, ct)); bis = FakeBis(last_sync_at=H0)
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.MINIMUM_WINDOW_CAPPED)
        self.assertIsNone(t["checkpoint_advanced_to"])
        self.assertEqual(bis.last_sync_at, H0)
        self.assertEqual(len(c.detail_calls), 0)
        self.assertEqual(len(self.min_alerts), 1)
        self._run("FES", bis, c, H0, ct)             # 2nd cycle -> dedupe
        self.assertEqual(len(self.min_alerts), 1)

    def test_transient_queued_advances_checkpoint(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(5, H0, ct), fail_detail={"O2": ao.OmisellError("t")})
        ao.order_retry = type("R", (), {"upsert": staticmethod(lambda b, n, e: True)})
        bis = FakeBis(last_sync_at=H0)
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(bis.last_sync_at, ct)

    def test_retry_persistence_failure_holds(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(5, H0, ct), fail_detail={"O2": ao.OmisellError("t")})
        ao.order_retry = type("R", (), {"upsert": staticmethod(lambda b, n, e: False)})
        bis = FakeBis(last_sync_at=H0)
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.RETRY_PERSISTENCE_FAILED)
        self.assertEqual(bis.last_sync_at, H0)
        self.assertIn(False, self.breaker)

    def test_probe_capped_no_side_effect(self):
        ct = H0 + timedelta(seconds=300); self._cap[0] = 2; self._min[0] = 300
        c = FakeClient(spread(50, H0, ct)); bis = FakeBis(last_sync_at=H0)
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.MINIMUM_WINDOW_CAPPED)
        self.assertEqual(len(c.detail_calls), 0)

    def test_stale_probe_undercount_still_splits(self):
        ct = H0 + timedelta(hours=1)
        c = FakeClient(spread(400, H0, ct), probe_override=10); bis = FakeBis()
        st, t = self._run("FES", bis, c, H0, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertGreaterEqual(t["split_depth"], 1)
        self.assertEqual(len(set(c.detail_calls)), 400)   # NO LOSS

    def test_lof_323_regression(self):
        cf = datetime(2026, 6, 13, 21, 16, 0); ct = cf + timedelta(hours=1)
        c = FakeClient(spread(323, cf, ct)); bis = FakeBis(last_sync_at=cf)
        st, t = self._run("LOF-VN", bis, c, cf, ct)
        self.assertEqual(st, swp.COMPLETED)
        self.assertEqual(t["split_depth"], 1)
        self.assertEqual(t["subwindows_processed"], 2)
        self.assertEqual(len(set(c.detail_calls)), 323)   # none lost (seam dedupes)
        self.assertEqual(bis.last_sync_at, ct)

    def test_budget_exhausted_holds_at_left(self):
        import time as _t
        ct = H0 + timedelta(hours=1); mid = swp.split_point(H0, ct); self._cap[0] = 5
        left = [("L%d" % i, E(H0) + 10 + i) for i in range(4)]
        right = [("R%d" % i, E(mid) + 10 + i) for i in range(4)]
        c = FakeClient(left + right)
        clk = type("C", (), {"now": 0.0})()
        saved_time = ao.time
        ao.time = type("T", (), {"monotonic": staticmethod(lambda: clk.now)})()
        real_detail = c.get_order_detail
        def ticking(n):
            clk.now += 10
            return real_detail(n)
        c.get_order_detail = ticking
        bis = FakeBis(last_sync_at=H0)
        tele = {"split_depth": 0, "subwindows_seen": 0, "subwindows_processed": 0,
                "checkpoint_advanced_to": None, "minimum_window_reached": False,
                "budget_exhausted": False, "stop_reason": None, "leaf_summaries": []}
        try:
            st = ao.pull_window_adaptive("FES", bis, c, H0, ct, 40, 0, tele)
        finally:
            ao.time = saved_time
        self.assertEqual(st, swp.BUDGET_EXHAUSTED)
        self.assertEqual(tele["subwindows_processed"], 1)
        self.assertEqual(tele["checkpoint_advanced_to"], str(mid))
        self.assertEqual(bis.last_sync_at, mid)


if __name__ == "__main__":
    unittest.main()
