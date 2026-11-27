# Copyright (c) 2026, eCentric and contributors
"""Doi tai khoan Kalodata (admin_service) tren repo / broker gia - khong can bench.

    python -m unittest ecentric_workspace.shared_tools.tests.test_admin
"""
import datetime as dt
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
fk = sys.modules.get("frappe") or types.ModuleType("frappe")
fk.conf = getattr(fk, "conf", {})
sys.modules["frappe"] = fk
fu = sys.modules.get("frappe.utils") or types.ModuleType("frappe.utils")
NOW = dt.datetime(2026, 11, 27, 15, 0)
fu.now_datetime = lambda: NOW
fu.add_days = getattr(fu, "add_days", lambda d, n: d)
sys.modules["frappe.utils"] = fu
if "requests" not in sys.modules:
    _rq = types.ModuleType("requests")
    _rq.RequestException = Exception
    sys.modules["requests"] = _rq

from ecentric_workspace.shared_tools import admin_service as A  # noqa: E402
from ecentric_workspace.shared_tools import constants as C  # noqa: E402
from ecentric_workspace.shared_tools import queue_rules as Q  # noqa: E402


class Fake:
    def __init__(self):
        self.enabled, self.log, self.notified, self.updates, self.resets = True, [], [], [], 0
        self.entries = [
            {"name": "A", "user": "a@x", "status": C.ST_ACTIVE, "started_at": NOW, "ends_at": NOW},
            {"name": "W", "user": "w@x", "status": C.ST_WAITING},
        ]


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.f = f = Fake()
        R, S, B = A.R, A.S, A.B
        self._saved = [(R, n, getattr(R, n)) for n in ("lock_tool", "set_tool_enabled", "open_entries", "log", "commit",
                                                       "notify", "publish_changed", "update_entry")]
        self._saved += [(S, "load_tool", S.load_tool), (B, "reset_profile", B.reset_profile)]
        R.lock_tool = lambda k: None
        R.set_tool_enabled = lambda k, on: setattr(f, "enabled", on)
        R.open_entries = lambda k: list(f.entries)
        R.log = lambda *a, **k: f.log.append(a[1])
        R.commit = lambda: None
        R.notify = lambda u, m, l: f.notified.append(u)
        R.publish_changed = lambda k: None
        R.update_entry = lambda n, v: f.updates.append((n, v["status"]))
        S.load_tool = lambda ctx, key: types.SimpleNamespace(title="Kalodata", ready_minutes=3)
        B.reset_profile = lambda: setattr(f, "resets", f.resets + 1)

    def tearDown(self):
        for mod, name, val in self._saved:
            setattr(mod, name, val)

    def test_reset_closes_tool_ends_all_and_wipes(self):
        ctx = A.S.Ctx("boss@x", ["System Manager"])
        out = A.reset_account(ctx, "kalodata")
        self.assertFalse(self.f.enabled)
        self.assertEqual(out["ended"], 2)
        self.assertEqual(dict(self.f.updates), {"A": C.ST_EXPIRED, "W": C.ST_CANCELLED})
        self.assertEqual(self.f.resets, 1)
        self.assertEqual(sorted(self.f.notified), ["a@x", "w@x"])
        self.assertIn(C.EV_MAINT, self.f.log)

    def test_non_manager_refused(self):
        with self.assertRaises(Q.QueueError):
            A.reset_account(A.S.Ctx("staff@x", ["Employee"]), "kalodata")
        self.assertTrue(self.f.enabled)
        self.assertEqual(self.f.resets, 0)

    def test_host_down_keeps_tool_closed_and_explains(self):
        def down():
            raise A.B.HostDown("Máy tắt.")
        A.B.reset_profile = down
        with self.assertRaises(Q.QueueError) as cm:
            A.reset_account(A.S.Ctx("boss@x", ["System Manager"]), "kalodata")
        self.assertIn("Đã đóng công cụ", str(cm.exception))
        self.assertFalse(self.f.enabled)

    def test_reopen(self):
        self.f.enabled = False
        self.assertTrue(A.set_enabled(A.S.Ctx("boss@x", ["EC Shared Tool Manager"]), "kalodata", True))
        self.assertTrue(self.f.enabled)


if __name__ == "__main__":
    unittest.main()
