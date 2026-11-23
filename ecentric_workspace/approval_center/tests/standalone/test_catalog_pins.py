# Copyright (c) 2026, eCentric and contributors
"""Approval Center ghim + hay dung (23/11/2026): set_pin chi dung toi ghim cua CHINH user dang nhap,
gioi han so ghim, bo ghim idempotent; _my_usage chi dem phieu cua chinh user. Chay code that
catalog_api.py (exec voi frappe gia), khong can site.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_catalog_pins.py
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.dirname(_APP))


class _Err(Exception):
    pass


class _World(object):
    def __init__(self):
        self.pins = []          # dicts: name, user, approval_type, pinned_at
        self.types = {"PAY", "LEAVE", "X%d" % 0}
        self.sql_args = None
        self.n = 0


def _load(world, user="a@x", internal=True):
    fk = types.ModuleType("frappe")
    fk.utils = types.ModuleType("frappe.utils")
    fk.utils.getdate = lambda v=None: v
    fk.utils.nowdate = lambda: "2026-11-23"
    fk.utils.now_datetime = lambda: "2026-11-23 10:00:%02d" % (world.n % 60)
    fk.utils.add_days = lambda d, n: "since(%s)" % n
    fk._ = lambda s: s
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _Err

    def throw(msg, exc=None):
        raise _Err(msg)
    fk.throw = throw

    class _Db(object):
        def exists(self, dt, name=None):
            if dt == "DocType":
                return True
            return name in world.types

        def sql(self, q, args=None, as_dict=False):
            world.sql_args = args
            return [types.SimpleNamespace(approval_type="PAY", n=4)]
    fk.db = _Db()

    def get_all(dt, filters=None, pluck=None, order_by=None, **k):
        rows = [p for p in world.pins if all(p.get(a) == b for a, b in (filters or {}).items())]
        rows.sort(key=lambda p: p["pinned_at"])
        return [p[pluck] for p in rows] if pluck else rows
    fk.get_all = get_all

    class _Doc(dict):
        def insert(self, ignore_permissions=False):
            world.n += 1
            self["name"] = "P%d" % world.n
            world.pins.append(dict(self))
            return self
    fk.get_doc = lambda d: _Doc({k: v for k, v in d.items() if k != "doctype"})

    def delete_doc(dt, name, **k):
        world.pins[:] = [p for p in world.pins if p["name"] != name]
    fk.delete_doc = delete_doc

    world.defaults = getattr(world, "defaults", {})
    fk.defaults = types.SimpleNamespace(
        get_user_default=lambda k, u: world.defaults.get((k, u)),
        set_user_default=lambda k, v, u: world.defaults.__setitem__((k, u), v))
    fk.cache = lambda: types.SimpleNamespace(get_value=lambda k: None, set_value=lambda *a, **k: None)

    perms = types.SimpleNamespace(is_internal_system_user=lambda u: internal)
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = fk
    sys.modules["frappe.utils"] = fk.utils
    src = io.open(os.path.join(_APP, "approval_center", "shared", "catalog_api.py"), encoding="utf-8").read()
    mod = types.ModuleType("catalog_api_pins")
    mod.__dict__["perms"] = perms
    exec(compile(src, "catalog_api.py", "exec"), mod.__dict__)
    mod.__dict__["perms"] = perms
    mod._restore = lambda: [sys.modules.__setitem__(k, v) if v else sys.modules.pop(k, None) for k, v in saved.items()]
    return mod


class Pins(unittest.TestCase):
    def setUp(self):
        self.w = _World()

    def _m(self, **k):
        m = _load(self.w, **k)
        self.addCleanup(m._restore)
        return m

    def test_pin_unpin_only_own(self):
        self.w.pins.append({"name": "OTHER", "user": "b@x", "approval_type": "PAY", "pinned_at": "0"})
        m = self._m(user="a@x")
        self.assertEqual(m.set_pin("PAY", 1)["my_pins"], ["PAY"])
        self.assertEqual(m.set_pin("PAY", 1)["my_pins"], ["PAY"], "ghim lai khong nhan doi")
        self.assertEqual(m.set_pin("LEAVE", "1")["my_pins"], ["PAY", "LEAVE"])
        self.assertEqual(m.set_pin("PAY", 0)["my_pins"], ["LEAVE"])
        self.assertTrue(any(p["user"] == "b@x" for p in self.w.pins), "ghim cua nguoi khac con nguyen")
        self.assertEqual(m.set_pin("PAY", "0")["my_pins"], ["LEAVE"], "bo ghim lan 2 khong loi")

    def test_limit_and_unknown_type(self):
        self.w.types |= {"T%d" % i for i in range(13)}
        m = self._m()
        for i in range(12):
            m.set_pin("T%d" % i, 1)
        with self.assertRaises(_Err):
            m.set_pin("T12", 1)
        with self.assertRaises(_Err):
            m.set_pin("KHONG_CO", 1)

    def test_external_user_denied(self):
        m = self._m(internal=False)
        with self.assertRaises(_Err):
            m.set_pin("PAY", 1)

    def test_usage_counts_only_own(self):
        m = self._m(user="a@x")
        self.assertEqual(m._my_usage("a@x"), {"PAY": 4})
        self.assertEqual(self.w.sql_args["u"], "a@x")
        self.assertEqual(self.w.sql_args["since"], "since(-90)")


class Seed(unittest.TestCase):
    def setUp(self):
        self.w = _World()
        self.w.types |= {"A", "B", "C", "D", "E"}

    def _m(self, usage, company, usable, **k):
        m = _load(self.w, **k)
        self.addCleanup(m._restore)
        m._my_usage = lambda u: usage
        m._company_top = lambda: company
        m.list_catalog = lambda: {"types": [{"approval_code": c, "route": "/x"} for c in usable]
                                  + [{"approval_code": "SOON", "route": None}]}
        return m

    def test_mine_first_then_company_only_usable(self):
        m = self._m({"B": 9, "SOON": 50, "A": 3}, ["SOON", "C", "B", "D", "E"], ["A", "B", "C", "D", "E"])
        self.assertEqual(m.seed_default_pins()["my_pins"], ["B", "A", "C", "D"])
        self.assertTrue(m._is_seeded("a@x"))

    def test_seed_runs_once_and_never_over_existing_pins(self):
        m = self._m({}, ["A", "B", "C", "D"], ["A", "B", "C", "D"])
        m.set_pin("E", 1)                      # tu ghim roi tu bo -> da danh dau, khong gieo
        m.set_pin("E", 0)
        self.assertEqual(m.seed_default_pins()["my_pins"], [], "user da tu chinh ghim -> khong gieo")
        self.assertEqual(m.seed_default_pins()["my_pins"], [])

    def test_external_user_gets_nothing(self):
        m = self._m({"A": 1}, ["B"], ["A", "B"], internal=False)
        self.assertEqual(m.seed_default_pins()["my_pins"], [])
        self.assertEqual(self.w.pins, [])


if __name__ == "__main__":
    unittest.main()
