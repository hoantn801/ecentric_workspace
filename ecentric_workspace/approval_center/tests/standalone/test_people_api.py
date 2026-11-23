# Copyright (c) 2026, eCentric and contributors
"""approval_center/api/people.search_users (24/11/2026, o chon nguoi dung chung): chi nguoi dung noi
bo da dang nhap goi duoc; tra dung ket qua danh ba dung chung. Chay code that voi frappe gia.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_people_api.py
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


class _Err(Exception):
    pass


def _load(user, internal):
    fk = types.ModuleType("frappe")
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _Err

    def throw(msg, exc=None):
        raise (exc or _Err)(msg)
    fk.throw = throw
    perms = types.SimpleNamespace(is_internal_system_user=lambda u: internal)
    calls = []
    people = types.SimpleNamespace(search_internal_users=lambda q: calls.append(q) or [{"user": "a@x"}])
    src = io.open(os.path.join(_APP, "approval_center", "api", "people.py"), encoding="utf-8").read()
    src = src.replace("import frappe\nfrom frappe import _\n", "").replace(
        "from ecentric_workspace.approval_center.shared import catalog_permissions as perms\n", "").replace(
        "from ecentric_workspace.approval_center.shared import people\n", "")
    mod = types.ModuleType("people_api_test")
    mod.__dict__.update({"frappe": fk, "_": fk._, "perms": perms, "people": people})
    exec(compile(src, "people.py", "exec"), mod.__dict__)
    return mod, calls


class SearchUsers(unittest.TestCase):
    def test_internal_user_gets_results(self):
        m, calls = _load("hoan@x", True)
        self.assertEqual(m.search_users("li"), [{"user": "a@x"}])
        self.assertEqual(calls, ["li"])

    def test_guest_and_website_user_denied(self):
        for user, internal in (("Guest", False), ("web@x", False), (None, True)):
            m, calls = _load(user, internal)
            with self.assertRaises(_Err):
                m.search_users("li")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
