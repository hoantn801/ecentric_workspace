# Copyright (c) 2026, eCentric and contributors
"""repository.py voi hinh dang THAT cua Frappe (Document con KHONG iterable, as_dict() doi bang con
thanh dict). Bat lai loi 500 /du-lieu 10/11/2026: dict(child_doc) -> TypeError
'ECDataSLARuleItem' object is not iterable. Bo fake cu dung dict nen khong thay.

    python -m unittest ecentric_workspace.data_hub.tests.test_repository_live_shapes
"""
import importlib
import sys
import types
import unittest


class _Child(object):
    """Giong frappe Document con: co .get() / thuoc tinh, KHONG iterable, KHONG la Mapping."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get(self, k, default=None):
        return self.__dict__.get(k, default)

    def as_dict(self):
        return dict(self.__dict__)

    def __iter__(self):
        raise TypeError("'ECDataSLARuleItem' object is not iterable")


class _Doc(object):
    def __init__(self, name, items):
        self.name = name
        self._items = items

    def get(self, k, default=None):
        return self._items if k == "items" else default

    def as_dict(self):
        return {"name": self.name, "status": "Đang áp dụng", "version_no": 1,
                "items": [c.as_dict() for c in self._items]}


def _install_fake():
    fk = types.ModuleType("frappe")
    fk.local = types.SimpleNamespace()
    fk.session = types.SimpleNamespace(user="a@x")
    docs = {"RS-1": _Doc("RS-1", [_Child(rule_key="pbi_new", label="Power BI mới", days=7, note="", idx=1),
                                 _Child(rule_key="crawl_new", label="Crawl data mới", days=7, note="x", idx=2)])}

    class _Db(object):
        def exists(self, dt, name=None):
            return name in docs if name is not None else True

    fk.db = _Db()
    fk.get_doc = lambda dt, name=None: docs[name]
    fk.get_all = lambda *a, **k: ["RS-1"] if k.get("pluck") else []
    fk.get_cached_doc = lambda dt: types.SimpleNamespace(get=lambda k, d=None: {"active_rule_set": "RS-1"}.get(k, d))
    fk._dict = dict
    return fk


class TestRuleSetLiveShape(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        sys.modules["frappe"] = _install_fake()
        sys.modules.pop("ecentric_workspace.data_hub.repository", None)
        self.R = importlib.import_module("ecentric_workspace.data_hub.repository")

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved)

    def test_rule_set_children_are_documents(self):
        rs = self.R.rule_set("RS-1")
        self.assertEqual(["pbi_new", "crawl_new"], [i["rule_key"] for i in rs["items"]])
        self.assertEqual(7, rs["items"][0]["days"])
        self.assertEqual({"rule_key", "label", "days", "note"}, set(rs["items"][1]))

    def test_rule_set_default_uses_active(self):
        rs = self.R.rule_set()
        self.assertEqual("RS-1", rs["name"])
        self.assertEqual(2, len(rs["items"]))


if __name__ == "__main__":
    unittest.main()
