# Copyright (c) 2026, eCentric and contributors
"""Phase 1b.3.1b -- governed, MARKER-SCOPED fulfillment ToDo lifecycle.

Bench-free: a minimal fake `frappe` backed by an in-memory ToDo table exercises
assign(fulfillment), the scoped close_fulfillment_todos, date-updating
ensure_sole_todo, reassign_fulfillment (eligibility), cancel_fulfillment
(authority), and the idempotent reconcile_fulfillment_todos. An UNRELATED Open
ToDo on the same document must survive every lifecycle op.
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))  # repo root
sys.path.insert(0, APP)


class _AttrDict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _match(row, filters):
    for k, v in (filters or {}).items():
        if isinstance(v, list) and v and v[0] == "in":
            if row.get(k) not in v[1]:
                return False
        elif row.get(k) != v:
            return False
    return True


class _DB:
    def __init__(self, store):
        self.s = store

    def _docs(self, dt, filters):
        if dt == "ToDo":
            return [r for r in self.s.todos if _match(r, filters or {})]
        rows = self.s.biz.get(dt, {})
        out = []
        for name, d in rows.items():
            rec = dict(d); rec["name"] = name
            if _match(rec, filters or {}):
                out.append(rec)
        return out

    def exists(self, dt, filters=None):
        return bool(self._docs(dt, filters))

    def get_value(self, dt, name, field=None, as_dict=False):
        if dt == "ToDo":
            rec = next((r for r in self.s.todos if r["name"] == name), None) or {}
        else:
            rec = dict(self.s.biz.get(dt, {}).get(name, {}))
        if isinstance(field, (list, tuple)):
            return _AttrDict({f: rec.get(f) for f in field}) if as_dict else {f: rec.get(f) for f in field}
        return rec.get(field)

    def set_value(self, dt, name, field, value=None, update_modified=True):
        if dt == "ToDo":
            rec = next((r for r in self.s.todos if r["name"] == name), None)
            if rec is None:
                return
        else:
            rec = self.s.biz.setdefault(dt, {}).setdefault(name, {})
        if isinstance(field, dict):
            rec.update(field)
        else:
            rec[field] = value

    def count(self, dt, filters=None):
        return len(self._docs(dt, filters))


class _Doc(dict):
    def __init__(self, store, data):
        super().__init__(data)
        self._store = store

    def insert(self, ignore_permissions=False):
        if self.get("doctype") == "ToDo":
            self._store.seq += 1
            row = dict(self); row["name"] = "TD-%03d" % self._store.seq
            row.setdefault("status", "Open")
            self._store.todos.append(row)
        elif self.get("doctype") == "EC Approval Action":
            self._store.actions.append(dict(self))
        elif self.get("doctype") == "Notification Log":
            self._store.notifs.append(dict(self))
        return self


class _Store:
    def __init__(self):
        self.todos = []
        self.biz = {}
        self.actions = []
        self.notifs = []
        self.roles = {}
        self.seq = 0


class _Frappe(types.ModuleType):
    def __init__(self, store):
        super().__init__("frappe")
        self.s = store
        self.db = _DB(store)
        self.session = types.SimpleNamespace(user="actor@e.c")
        self.flags = types.SimpleNamespace(mute_messages=False, ignore_permissions=False)
        self.local = types.SimpleNamespace(message_log=[])
        self.utils = types.SimpleNamespace(now_datetime=lambda: "2026-07-28 10:00:00",
                                           add_to_date=lambda *a, **k: "2026-07-30 10:00:00")
        self.share = types.SimpleNamespace(add_docshare=lambda *a, **k: None, add=lambda *a, **k: None)
        self._ = lambda s: s

    def get_doc(self, data):
        return _Doc(self.s, data)

    def get_all(self, dt, filters=None, fields=None, **k):
        rows = self.db._docs(dt, filters)
        if fields:
            rows = [{f: r.get(f) for f in fields} for r in rows]
        return [_AttrDict(r) for r in rows]

    def get_roles(self, user=None):
        return list(self.s.roles.get(user or self.session.user, []))

    def throw(self, msg, exc=None):
        raise Exception(msg)

    def parse_json(self, v):
        import json
        return json.loads(v) if isinstance(v, str) else (v or [])

    def as_json(self, v):
        import json
        return json.dumps(v)

    class PermissionError(Exception):
        pass


STORE = _Store()
FR = _Frappe(STORE)
FR.__path__ = []
sys.modules["frappe"] = FR
_utils = types.ModuleType("frappe.utils")
_utils.now_datetime = lambda: "2026-07-28 10:00:00"
_utils.add_to_date = lambda *a, **k: "x"
_utils.getdate = lambda v: str(v)[:10]        # date-only normalization for tests
sys.modules["frappe.utils"] = _utils
_share = types.ModuleType("frappe.share")
_share.add_docshare = lambda *a, **k: None
_share.add = lambda *a, **k: None
sys.modules["frappe.share"] = _share

from ecentric_workspace.approval_center.engine import service as engine  # noqa: E402

BIZ = "EC System Request"


def _reset():
    STORE.todos.clear(); STORE.biz.clear(); STORE.actions.clear(); STORE.notifs.clear()
    STORE.roles.clear(); STORE.seq = 0


def _open(name=None, user=None):
    out = [t for t in STORE.todos if t["status"] == "Open"]
    if name: out = [t for t in out if t["reference_name"] == name]
    if user: out = [t for t in out if t["allocated_to"] == user]
    return out


def _open_fulfillment(name=None):
    return [t for t in _open(name) if t.get("ec_fulfillment") == 1]


class TestMarkerScopedLifecycle(unittest.TestCase):
    """The lifecycle ops touch ONLY marked fulfillment ToDos; an unrelated Open
    ToDo on the same business document survives claim/reassign/cancel/complete."""

    def setUp(self):
        _reset()
        STORE.biz[BIZ] = {"SR-1": {"fulfillment_status": "Assigned", "fulfillment_owner": "",
                                   "fulfillment_due_at": "2026-07-30 09:00:00",
                                   "approval_request": "REQ-1", "requested_by": "req@e.c"}}
        # an UNRELATED (unmarked) Open ToDo on the same document
        STORE.todos.append({"name": "TD-UNREL", "reference_type": BIZ, "reference_name": "SR-1",
                            "allocated_to": "someone@e.c", "status": "Open"})

    def _unrelated_open(self):
        return any(t["name"] == "TD-UNREL" and t["status"] == "Open" for t in STORE.todos)

    def test_assign_marks_pool_and_sets_date(self):
        engine.assign(BIZ, "SR-1", ["a@e.c", "b@e.c"], "queue",
                      date="2026-07-30 09:00:00", fulfillment=True)
        opens = _open_fulfillment("SR-1")
        self.assertEqual(len(opens), 2)
        self.assertTrue(all(t.get("date") == "2026-07-30 09:00:00" for t in opens))
        self.assertTrue(self._unrelated_open())         # unrelated untouched

    def test_close_fulfillment_todos_is_scoped(self):
        engine.assign(BIZ, "SR-1", ["a@e.c", "b@e.c"], "queue", fulfillment=True)
        engine.close_fulfillment_todos(BIZ, "SR-1")
        self.assertEqual(_open_fulfillment("SR-1"), [])   # marked closed
        self.assertTrue(self._unrelated_open())           # unrelated survives

    def test_claim_ensure_sole_todo_keeps_unrelated(self):
        engine.assign(BIZ, "SR-1", ["a@e.c", "b@e.c", "c@e.c"], "queue", fulfillment=True)
        engine.ensure_sole_todo(BIZ, "SR-1", "b@e.c", "queue", date="2026-07-30 09:00:00")
        f = _open_fulfillment("SR-1")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["allocated_to"], "b@e.c")
        self.assertTrue(self._unrelated_open())

    def test_system_manager_not_in_pool_gets_exactly_one_marked(self):
        engine.assign(BIZ, "SR-1", ["a@e.c", "b@e.c"], "queue", fulfillment=True)
        engine.ensure_sole_todo(BIZ, "SR-1", "sm@e.c", "queue", date="2026-07-30 09:00:00")
        f = _open_fulfillment("SR-1")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["allocated_to"], "sm@e.c")
        self.assertEqual(f[0]["date"], "2026-07-30 09:00:00")
        self.assertTrue(self._unrelated_open())

    def test_ensure_updates_existing_todo_old_date_and_marks_it(self):
        # a pre-existing UNMARKED Open ToDo with an OLD date -> upgraded in place.
        STORE.todos.append({"name": "TD-OLD", "reference_type": BIZ, "reference_name": "SR-1",
                            "allocated_to": "own@e.c", "status": "Open", "date": "2000-01-01"})
        engine.ensure_sole_todo(BIZ, "SR-1", "own@e.c", "queue", date="2026-07-30 09:00:00")
        td = next(t for t in STORE.todos if t["name"] == "TD-OLD")
        self.assertEqual(td["date"], "2026-07-30 09:00:00")   # updated to fulfillment_due_at
        self.assertEqual(td.get("ec_fulfillment"), 1)         # marked
        self.assertEqual(len(_open_fulfillment("SR-1")), 1)   # no duplicate
        self.assertTrue(self._unrelated_open())

    def test_cancel_scoped_keeps_unrelated(self):
        STORE.biz[BIZ]["SR-1"].update(fulfillment_status="In Progress", fulfillment_owner="own@e.c")
        STORE.roles["sm@e.c"] = ["System Manager"]
        engine.assign(BIZ, "SR-1", ["own@e.c"], "queue", fulfillment=True)
        engine.cancel_fulfillment(BIZ, "SR-1", actor="sm@e.c")
        self.assertEqual(_open_fulfillment("SR-1"), [])
        self.assertEqual(STORE.biz[BIZ]["SR-1"]["fulfillment_status"], "Cancelled")
        self.assertTrue(self._unrelated_open())


class TestReassignAuthorityAndEligibility(unittest.TestCase):
    def setUp(self):
        _reset()
        STORE.biz[BIZ] = {"SR-1": {"fulfillment_status": "In Progress", "fulfillment_owner": "old@e.c",
                                   "fulfillment_due_at": "2026-07-30 09:00:00",
                                   "approval_request": "REQ-1", "requested_by": "req@e.c"}}
        STORE.biz["User"] = {"new@e.c": {"enabled": 1}, "disabled@e.c": {"enabled": 0}}
        engine.assign(BIZ, "SR-1", ["old@e.c"], "queue", fulfillment=True)
        self._orig = engine._resolve_fulfillers
        engine._resolve_fulfillers = lambda ar, rb: {"new@e.c"}   # new@e.c is eligible

    def tearDown(self):
        engine._resolve_fulfillers = self._orig

    def test_reassign_owner_to_eligible_enabled(self):
        engine.reassign_fulfillment(BIZ, "SR-1", "new@e.c", actor="old@e.c", description="queue")
        f = _open_fulfillment("SR-1")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["allocated_to"], "new@e.c")     # old closed, new ensured
        self.assertEqual(STORE.biz[BIZ]["SR-1"]["fulfillment_owner"], "new@e.c")

    def test_reassign_rejects_ineligible_target(self):
        engine._resolve_fulfillers = lambda ar, rb: set()       # nobody eligible
        with self.assertRaises(Exception):
            engine.reassign_fulfillment(BIZ, "SR-1", "new@e.c", actor="old@e.c")

    def test_reassign_rejects_disabled_target(self):
        engine._resolve_fulfillers = lambda ar, rb: {"disabled@e.c"}
        with self.assertRaises(Exception):
            engine.reassign_fulfillment(BIZ, "SR-1", "disabled@e.c", actor="old@e.c")

    def test_reassign_requires_owner_or_sm(self):
        with self.assertRaises(Exception):
            engine.reassign_fulfillment(BIZ, "SR-1", "new@e.c", actor="stranger@e.c")


class TestCancelAuthority(unittest.TestCase):
    def setUp(self):
        _reset()
        STORE.biz[BIZ] = {"SR-1": {"fulfillment_status": "In Progress", "fulfillment_owner": "own@e.c",
                                   "fulfillment_due_at": "d", "approval_request": "REQ-1",
                                   "requested_by": "req@e.c"}}
        engine.assign(BIZ, "SR-1", ["own@e.c"], "queue", fulfillment=True)

    def test_owner_alone_cannot_cancel(self):
        with self.assertRaises(Exception):     # explicit authority: not every owner
            engine.cancel_fulfillment(BIZ, "SR-1", actor="own@e.c")

    def test_system_manager_can_cancel(self):
        STORE.roles["sm@e.c"] = ["System Manager"]
        engine.cancel_fulfillment(BIZ, "SR-1", actor="sm@e.c")
        self.assertEqual(STORE.biz[BIZ]["SR-1"]["fulfillment_status"], "Cancelled")

    def test_cancel_requires_active(self):
        STORE.biz[BIZ]["SR-1"]["fulfillment_status"] = "Completed"
        STORE.roles["sm@e.c"] = ["System Manager"]
        with self.assertRaises(Exception):
            engine.cancel_fulfillment(BIZ, "SR-1", actor="sm@e.c")


class TestReconciliation(unittest.TestCase):
    """Idempotent reconciliation of active fulfillment records missing ToDos."""

    def setUp(self):
        _reset()
        self._orig = engine._resolve_fulfillers
        engine._resolve_fulfillers = lambda ar, rb: {"f1@e.c", "f2@e.c"}

    def tearDown(self):
        engine._resolve_fulfillers = self._orig

    def _req_approved(self, req="REQ-1"):
        STORE.biz["EC Approval Request"] = STORE.biz.get("EC Approval Request", {})
        STORE.biz["EC Approval Request"][req] = {"approval_status": "Approved"}

    def test_owner_missing_todo_is_created_and_scoped(self):
        STORE.biz[BIZ] = {"SR-1": {"fulfillment_status": "In Progress", "fulfillment_owner": "own@e.c",
                                   "fulfillment_due_at": "2026-07-30 09:00:00",
                                   "approval_request": "REQ-1", "requested_by": "req@e.c"}}
        engine._resolve_fulfillers = lambda ar, rb: {"own@e.c"}
        res = engine.reconcile_fulfillment_todos([BIZ])
        f = _open_fulfillment("SR-1")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["allocated_to"], "own@e.c")
        self.assertEqual(f[0]["date"], "2026-07-30 09:00:00")
        self.assertEqual(res["before"], 0)
        self.assertEqual(res["after"], 1)

    def test_no_owner_pool_one_per_fulfiller(self):
        STORE.biz[BIZ] = {"SR-2": {"fulfillment_status": "Assigned", "fulfillment_owner": "",
                                   "fulfillment_due_at": "d", "approval_request": "REQ-1",
                                   "requested_by": "req@e.c"}}
        engine.reconcile_fulfillment_todos([BIZ])
        users = {t["allocated_to"] for t in _open_fulfillment("SR-2")}
        self.assertEqual(users, {"f1@e.c", "f2@e.c"})

    def test_terminal_closes_all_fulfillment(self):
        STORE.biz[BIZ] = {"SR-3": {"fulfillment_status": "Completed", "fulfillment_owner": "own@e.c",
                                   "fulfillment_due_at": "d", "approval_request": "REQ-1",
                                   "requested_by": "req@e.c"}}
        # a lingering fulfillment ToDo allocated to the owner (a participant)
        STORE.todos.append({"name": "TD-L", "reference_type": BIZ, "reference_name": "SR-3",
                            "allocated_to": "own@e.c", "status": "Open"})
        engine._resolve_fulfillers = lambda ar, rb: {"own@e.c"}
        engine.reconcile_fulfillment_todos([BIZ])
        self.assertEqual(_open("SR-3"), [])          # closed

    def test_reconcile_is_idempotent(self):
        STORE.biz[BIZ] = {"SR-4": {"fulfillment_status": "In Progress", "fulfillment_owner": "own@e.c",
                                   "fulfillment_due_at": "2026-07-30 09:00:00",
                                   "approval_request": "REQ-1", "requested_by": "req@e.c"}}
        engine._resolve_fulfillers = lambda ar, rb: {"own@e.c"}
        r1 = engine.reconcile_fulfillment_todos([BIZ])
        snapshot = [(t["name"], t["status"], t.get("date"), t.get("ec_fulfillment")) for t in STORE.todos]
        r2 = engine.reconcile_fulfillment_todos([BIZ])
        snapshot2 = [(t["name"], t["status"], t.get("date"), t.get("ec_fulfillment")) for t in STORE.todos]
        self.assertEqual(snapshot, snapshot2)         # second run: no changes
        self.assertEqual(r2["before"], r2["after"])
        self.assertEqual(r1["after"], r2["after"])

    def test_reconcile_does_not_touch_unrelated_todo(self):
        STORE.biz[BIZ] = {"SR-5": {"fulfillment_status": "In Progress", "fulfillment_owner": "own@e.c",
                                   "fulfillment_due_at": "d", "approval_request": "REQ-1",
                                   "requested_by": "req@e.c"}}
        STORE.todos.append({"name": "TD-U", "reference_type": BIZ, "reference_name": "SR-5",
                            "allocated_to": "unrelated@e.c", "status": "Open"})
        engine._resolve_fulfillers = lambda ar, rb: {"own@e.c"}
        engine.reconcile_fulfillment_todos([BIZ])
        self.assertTrue(any(t["name"] == "TD-U" and t["status"] == "Open" for t in STORE.todos))


class TestProducerWiring(unittest.TestCase):
    """Every producer reuses the engine lifecycle (no direct inserts), marks pool
    ToDos, closes scoped on completion, and does NOT expose reassign/cancel."""

    FORMS = ["ai_topup", "asset_request", "data_request", "document_request",
             "resignation", "system_request"]

    def _src(self, module):
        p = os.path.join(APP, "ecentric_workspace", "approval_center", module, "service.py")
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    def test_on_final_approval_marks_pool_with_due_date(self):
        for m in self.FORMS:
            src = self._src(m)
            self.assertIn("engine.assign(", src, m)
            self.assertIn('date=sla["due_at"] if sla else None', src, m)
            self.assertIn("fulfillment=True", src, m)

    def test_claim_uses_ensure_sole_todo(self):
        for m in self.FORMS:
            src = self._src(m)
            self.assertIn("engine.ensure_sole_todo(", src, m)
            self.assertIn('"fulfillment_due_at"', src, m)
            self.assertNotIn("close_todos(BUSINESS_DT, name, keep_user=user)", src, m)

    def test_completion_uses_scoped_close(self):
        for m in self.FORMS:
            src = self._src(m)
            self.assertIn("engine.close_fulfillment_todos(BUSINESS_DT, name)", src, m)
            self.assertNotIn("engine.close_todos(BUSINESS_DT, name)", src, m)  # not the broad close

    def test_reassign_cancel_not_exposed(self):
        # B3: no governed UI use case -> no whitelisted producer endpoints.
        for m in self.FORMS:
            src = self._src(m)
            self.assertNotIn("def reassign_fulfillment(name", src, m)
            self.assertNotIn("def cancel_fulfillment(name", src, m)

    def test_no_direct_todo_inserts_in_producers(self):
        for m in self.FORMS:
            src = self._src(m)
            self.assertNotIn('"doctype": "ToDo"', src, m)
            self.assertNotIn("'doctype': 'ToDo'", src, m)

    def test_marker_patch_and_fixture_registered(self):
        patches = open(os.path.join(APP, "ecentric_workspace", "patches.txt"), encoding="utf-8").read()
        self.assertIn("approval_center.patches.p044_todo_fulfillment_marker", patches)
        hooks = open(os.path.join(APP, "ecentric_workspace", "hooks.py"), encoding="utf-8").read()
        self.assertIn("ToDo-ec_fulfillment", hooks)


if __name__ == "__main__":
    unittest.main()
