# Copyright (c) 2026, eCentric and contributors
"""Luat hang doi Kalodata dung chung (ham thuan) + chu ky broker - khong can bench.

    python -m unittest ecentric_workspace.shared_tools.tests.test_queue
"""
import datetime as dt
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
if "frappe" not in sys.modules:
    _fk = types.ModuleType("frappe")
    _fk.conf = {}
    sys.modules["frappe"] = _fk
if "requests" not in sys.modules:
    _rq = types.ModuleType("requests")
    _rq.RequestException = Exception
    sys.modules["requests"] = _rq

from ecentric_workspace.shared_tools import broker_client as B  # noqa: E402
from ecentric_workspace.shared_tools import constants as C  # noqa: E402
from ecentric_workspace.shared_tools import queue_rules as Q  # noqa: E402

NOW = dt.datetime(2026, 11, 27, 14, 0)
CFG = Q.cfg_of({})
M = Q.minutes


def e(name, user, status, joined=-60, **kw):
    row = {"name": name, "user": user, "status": status, "joined_at": NOW + M(joined), "extended": 0}
    row.update(kw)
    return row


def active(name="A", user="a@x", started=-5, ends=25, **kw):
    return e(name, user, C.ST_ACTIVE, joined=-90, started_at=NOW + M(started), ends_at=NOW + M(ends), **kw)


HOST_BUSY = {"ok": True, "vnc_clients": 1, "x_idle_ms": 1000, "current_user": "a@x"}


class TickTest(unittest.TestCase):
    def test_first_waiting_becomes_ready_when_nobody_holds(self):
        out = Q.tick([e("W2", "c@x", C.ST_WAITING, -1), e("W1", "b@x", C.ST_WAITING, -5)], NOW, CFG)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "W1")
        self.assertEqual(out[0]["set"], {"status": C.ST_READY, "ready_at": NOW})
        self.assertTrue(out[0]["notify"])

    def test_nobody_promoted_while_someone_active(self):
        self.assertEqual(Q.tick([active(), e("W1", "b@x", C.ST_WAITING)], NOW, CFG, HOST_BUSY), [])

    def test_lease_over_completes_revokes_and_promotes_next(self):
        out = Q.tick([active(started=-31, ends=-1), e("W1", "b@x", C.ST_WAITING)], NOW, CFG, HOST_BUSY)
        self.assertEqual([c["name"] for c in out], ["A", "W1"])
        self.assertEqual(out[0]["set"]["status"], C.ST_COMPLETED)
        self.assertEqual(out[0]["set"]["end_reason"], C.END_TIME)
        self.assertTrue(out[0]["revoke"])
        self.assertEqual(out[1]["set"]["status"], C.ST_READY)

    def test_ready_not_opened_in_time_is_skipped(self):
        out = Q.tick([e("R", "b@x", C.ST_READY, ready_at=NOW - M(3)), e("W", "c@x", C.ST_WAITING)], NOW, CFG)
        self.assertEqual(out[0]["set"]["status"], C.ST_SKIPPED)
        self.assertEqual(out[0]["set"]["end_reason"], C.END_NO_SHOW)
        self.assertFalse(out[0].get("revoke"))
        self.assertEqual(out[1]["name"], "W")

    def test_ready_still_inside_window_stays(self):
        self.assertEqual(Q.tick([e("R", "b@x", C.ST_READY, ready_at=NOW - M(2))], NOW, CFG), [])

    def test_idle_no_viewer_expires_after_idle_minutes(self):
        host = dict(HOST_BUSY, vnc_clients=0)
        out = Q.tick([active(started=-11)], NOW, CFG, host)
        self.assertEqual(out[0]["set"]["status"], C.ST_EXPIRED)
        self.assertEqual(out[0]["set"]["end_reason"], C.END_IDLE)

    def test_idle_input_counts_even_with_viewer(self):
        host = dict(HOST_BUSY, x_idle_ms=10 * 60 * 1000)
        self.assertEqual(Q.tick([active(started=-15)], NOW, CFG, host)[0]["set"]["status"], C.ST_EXPIRED)

    def test_busy_export_not_idle(self):
        host = dict(HOST_BUSY, vnc_clients=0, busy=True)
        self.assertEqual(Q.tick([active(started=-20)], NOW, CFG, host), [])
        self.assertEqual(Q.tick([active(started=-31, ends=-1)], NOW, CFG, host)[0]["set"]["status"], C.ST_COMPLETED)

    def test_just_started_not_idle(self):
        host = dict(HOST_BUSY, vnc_clients=0)
        self.assertEqual(Q.tick([active(started=-2)], NOW, CFG, host), [])

    def test_host_down_never_idle_expires(self):
        self.assertEqual(Q.tick([active(started=-20)], NOW, CFG, {"ok": False}), [])
        self.assertEqual(Q.tick([active(started=-20)], NOW, CFG, None), [])


class CommandTest(unittest.TestCase):
    def test_join_twice_refused(self):
        with self.assertRaises(Q.QueueError):
            Q.can_join([e("W", "b@x", C.ST_WAITING)], "b@x")
        Q.can_join([e("W", "b@x", C.ST_COMPLETED)], "b@x")

    def test_start_ready_sets_lease(self):
        v = Q.start(e("R", "b@x", C.ST_READY, ready_at=NOW), NOW, CFG)
        self.assertEqual(v["status"], C.ST_ACTIVE)
        self.assertEqual(v["ends_at"], NOW + M(30))

    def test_start_active_reopens_without_change(self):
        self.assertEqual(Q.start(active(), NOW, CFG), {})

    def test_start_waiting_refused(self):
        with self.assertRaises(Q.QueueError):
            Q.start(e("W", "b@x", C.ST_WAITING), NOW, CFG)
        with self.assertRaises(Q.QueueError):
            Q.start(None, NOW, CFG)

    def test_extend_blocked_by_waiters(self):
        es = [active(ends=5), e("W", "b@x", C.ST_WAITING), e("W2", "c@x", C.ST_WAITING)]
        self.assertIn("2 người", Q.extend_check(es, es[0], NOW))
        with self.assertRaises(Q.QueueError):
            Q.extend(es, es[0], NOW, CFG)

    def test_extend_only_near_end(self):
        es = [active(ends=22)]
        self.assertIn("dưới 10 phút", Q.extend_check(es, es[0], NOW))
        es = [active(ends=8)]
        self.assertIsNone(Q.extend_check(es, es[0], NOW))
        v = Q.extend(es, es[0], NOW, CFG)
        self.assertEqual(v["ends_at"], NOW + M(23))
        self.assertEqual(v["extended"], 1)

    def test_leave_maps_status(self):
        self.assertEqual(Q.leave(e("W", "b@x", C.ST_WAITING), NOW)["set"]["status"], C.ST_CANCELLED)
        self.assertEqual(Q.leave(e("R", "b@x", C.ST_READY), NOW)["set"]["status"], C.ST_SKIPPED)
        out = Q.leave(active(), NOW)
        self.assertEqual(out["set"]["status"], C.ST_COMPLETED)
        self.assertTrue(out["revoke"])

    def test_reconcile_revoke(self):
        host = {"ok": True, "current_user": "a@x"}
        self.assertFalse(Q.needs_reconcile_revoke([active()], host))
        self.assertTrue(Q.needs_reconcile_revoke([], host))
        self.assertFalse(Q.needs_reconcile_revoke([], {"ok": True, "current_user": ""}))
        self.assertFalse(Q.needs_reconcile_revoke([], {"ok": False, "current_user": "a@x"}))

    def test_eta(self):
        es = [active(ends=22), e("W1", "b@x", C.ST_WAITING, -10), e("W2", "c@x", C.ST_WAITING, -5)]
        self.assertEqual(Q.eta_minutes(es, es[1], NOW, CFG), 22)
        self.assertEqual(Q.eta_minutes(es, es[2], NOW, CFG), 52)


class BomTest(unittest.TestCase):
    def test_csv_gets_bom_once(self):
        sys.modules.setdefault("frappe.utils", types.ModuleType("frappe.utils"))
        fu = sys.modules["frappe.utils"]
        fu.add_days = getattr(fu, "add_days", lambda d, n: d)
        fu.now_datetime = getattr(fu, "now_datetime", lambda: NOW)
        from ecentric_workspace.shared_tools import exports as X
        self.assertEqual(X.with_bom("a.csv", "Cột,1"), X.BOM + "Cột,1".encode())
        self.assertEqual(X.with_bom("a.CSV", X.BOM + b"x"), X.BOM + b"x")
        self.assertEqual(X.with_bom("a.xlsx", b"PK"), b"PK")


class SignTest(unittest.TestCase):
    def test_signature_binds_method_path_body(self):
        s = B.sign("k", "POST", "/ec/grant", 100, "n", b'{"user":"a"}')
        self.assertEqual(len(s), 64)
        self.assertNotEqual(s, B.sign("k", "POST", "/ec/revoke", 100, "n", b'{"user":"a"}'))
        self.assertNotEqual(s, B.sign("k", "POST", "/ec/grant", 100, "n", b'{"user":"b"}'))
        self.assertNotEqual(s, B.sign("k", "GET", "/ec/grant", 100, "n", b'{"user":"a"}'))
        self.assertNotEqual(s, B.sign("k2", "POST", "/ec/grant", 100, "n", b'{"user":"a"}'))


if __name__ == "__main__":
    unittest.main()
