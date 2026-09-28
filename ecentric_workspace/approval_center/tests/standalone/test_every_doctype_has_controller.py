# Copyright (c) 2026, eCentric and contributors
"""Moi thu muc DocType trong repo phai co <ten>.py canh <ten>.json.

Vi sao: Frappe import module cua MOI DocType khi migrate (DocType.on_update ->
on_doctype_update). Thieu file .py - ke ca bang con khong co logic - la
ModuleNotFoundError giua chung migrate, va Frappe Cloud rollback CA dot deploy.
Da xay ra 25/09 voi EC Brand Weight Request Detail. tools/ci/check.py chi kiem cu
phap, khong chay migrate, nen khong bat duoc loi nay."""
import os
import unittest

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _doctype_dirs():
    for root, dirs, files in os.walk(_APP):
        if os.path.basename(os.path.dirname(root)) != "doctype":
            continue
        name = os.path.basename(root)
        if name + ".json" in files:
            yield root, name, files


class TestMoiDoctypeCoController(unittest.TestCase):
    def test_moi_doctype_co_file_py(self):
        checked, missing = 0, []
        for root, name, files in _doctype_dirs():
            checked += 1
            if name + ".py" not in files:
                missing.append(os.path.relpath(os.path.join(root, name + ".py"), _APP))
        self.assertGreater(checked, 50, "bo quet khong tim thay DocType nao - duong dan sai?")
        self.assertEqual([], missing, "DocType thieu controller, migrate se chet: %s" % missing)


if __name__ == "__main__":
    unittest.main()
