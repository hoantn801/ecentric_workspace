# Copyright (c) 2026, eCentric and contributors
"""The patch that removes a participant row must never be able to block submitting.

Emptying a level's approver sources makes build_snapshot throw for every requester - nobody
can send a Payment Request at all. A migration that can do that silently is worse than one
that does nothing, so it refuses and says so instead.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root, tried = _HERE, []
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % parts[-1])


_P = _src("approval_center", "patches",
          "p100_drop_requester_manager_from_payment_level1.py")


class _Row(object):
    def __init__(self, st, purpose="Approver"):
        self.source_type = st
        self.participant_purpose = purpose


class _Doc(object):
    def __init__(self, rows):
        self.participants = list(rows)
        self.saved = False

    def set(self, field, value):
        setattr(self, field, value)

    def save(self, **kw):
        self.saved = True


def _run(rows, levels=(("LVL-1",),)):
    doc = _Doc(rows)
    logged = []

    class _Logger(object):
        def info(self, m):
            logged.append(("info", m))

        def error(self, m):
            logged.append(("error", m))

    class _Frappe(object):
        @staticmethod
        def get_all(dt, **kw):
            # Frappe tra ve _dict (truy cap bang thuoc tinh). Stub tra dict thuong se lam
            # `lvl.name` no AttributeError - mot khac biet cua stub, khong phai cua code.
            return [type("R", (), {"name": n[0]})() for n in levels]

        @staticmethod
        def get_doc(dt, name):
            return doc

        @staticmethod
        def logger():
            return _Logger()

    # Bo dong `import frappe` o dau file: o day khong co Frappe that, va cai minh muon
    # nghiem thu la HANH VI cua execute() chu khong phai kha nang import.
    src = re.sub(r"(?m)^import frappe$", "", _P)
    g = {"frappe": _Frappe()}
    exec(compile(src, "p100", "exec"), g)
    g["execute"]()
    return doc, logged


class TestItRemovesOnlyTheOneRow(unittest.TestCase):
    def test_the_requester_manager_row_goes(self):
        doc, _l = _run([_Row("Department Manager"), _Row("Requester Manager")])
        self.assertEqual([r.source_type for r in doc.participants], ["Department Manager"])
        self.assertTrue(doc.saved)

    def test_running_twice_changes_nothing(self):
        doc, logged = _run([_Row("Department Manager")])
        self.assertFalse(doc.saved, "khong co gi de xoa ma van ghi = sua vo co")
        self.assertTrue(any("already has no" in m for _k, m in logged))


class TestItRefusesToBlockEveryone(unittest.TestCase):
    def test_it_will_not_empty_the_level(self):
        doc, logged = _run([_Row("Requester Manager")])
        self.assertFalse(doc.saved, "xoa het nguon nguoi duyet = khong ai gui duoc yeu cau")
        self.assertEqual([r.source_type for r in doc.participants], ["Requester Manager"])
        self.assertTrue(any(k == "error" for k, _m in logged),
                        "tu choi thi phai NOI RA, khong im lang")

    def test_the_guard_is_present_in_source(self):
        self.assertIn("if not keep:", _P)
        self.assertIn("refusing to empty", _P)


if __name__ == "__main__":
    unittest.main()
