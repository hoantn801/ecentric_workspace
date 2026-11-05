# Copyright (c) 2026, eCentric and contributors
"""p008: cay bao cao Employee duoc tinh lai sau deploy (case Thu Trinh Minh / nhom chi Phuong).

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_rebuild_employee_tree
"""
import importlib
import os
import sys
import types
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TestRebuildEmployeeTree(unittest.TestCase):
    def _run(self, sig2=True):
        calls, logs = [], []
        fr = types.ModuleType("frappe")
        fr.db = types.SimpleNamespace(sql=lambda *a, **k: [])
        fr.log_error = lambda title=None, message=None: logs.append((title, message))
        fr.get_traceback = lambda: "tb"
        ns = types.ModuleType("frappe.utils.nestedset")

        def rebuild_tree(doctype, parent_field=None):
            if not sig2 and parent_field is not None:
                raise TypeError("v15 chi nhan doctype")
            calls.append((doctype, parent_field))
        ns.rebuild_tree = rebuild_tree
        ut = types.ModuleType("frappe.utils")
        ut.nestedset = ns
        sys.modules.update({"frappe": fr, "frappe.utils": ut, "frappe.utils.nestedset": ns})
        try:
            m = importlib.import_module("ecentric_workspace.hr.patches.p008_rebuild_employee_tree")
            importlib.reload(m)
            m.execute()
        finally:
            for k in ("frappe", "frappe.utils", "frappe.utils.nestedset"):
                sys.modules.pop(k, None)
        return calls, logs

    def test_rebuild_dung_cay_employee(self):
        calls, logs = self._run()
        self.assertEqual(calls, [("Employee", "reports_to")])
        self.assertIn("lech truoc", logs[-1][1])

    def test_frappe_moi_chi_nhan_doctype(self):
        calls, _ = self._run(sig2=False)
        self.assertEqual(calls, [("Employee", None)])

    def test_dang_ky_trong_patches(self):
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("ecentric_workspace.hr.patches.p008_rebuild_employee_tree", fh.read())


if __name__ == "__main__":
    unittest.main()
