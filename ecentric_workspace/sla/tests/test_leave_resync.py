# Copyright (c) 2026, eCentric and contributors
"""Phep duyet tre phai lam ngay nghi thanh "Khong tinh diem". KHONG import frappe.

30/09/2026: phieu nghi 18/09 duoc duyet ngay 30/09 - ngoai cua so 7 ngay cua job
dem - nen ngay 18/09 nam `Open` va hien "Chua lam" vinh vien.
"""
import ast
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SLA = os.path.join(HERE, "..")
APP = os.path.join(SLA, "..")


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def _func(src, name):
    body = src[src.index("def %s(" % name):]
    nxt = body.find("\ndef ", 1)
    return body if nxt == -1 else body[:nxt]


class TestHookDuyetPhep(unittest.TestCase):
    def test_hooks_py_dang_ky_on_submit(self):
        src = _read(APP, "hooks.py")
        self.assertIn('"ecentric_workspace.sla.application.hooks.on_leave_application_submit"', src)
        self.assertIn('doc_events.setdefault("Leave Application", {})', src)
        self.assertIn('_sla_la.get("on_submit")', src)

    def test_ham_hook_ton_tai_va_nuot_loi(self):
        src = _read(SLA, "application", "hooks.py")
        tree = ast.parse(src)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertIn("on_leave_application_submit", names)
        body = _func(src, "on_leave_application_submit")
        self.assertIn("except Exception", body)
        self.assertIn('"Approved"', body, "chi dong bo khi phieu DA duyet")
        self.assertIn("attendance_source.sync_leave", body)

    def test_sync_leave_khong_viet_lai_luat(self):
        src = _read(SLA, "infrastructure", "attendance_source.py")
        body = _func(src, "sync_leave")
        self.assertIn("_sync_employee(", body, "phai dung chung bo luat voi job dem")
        self.assertNotIn("ar.decide(", body)
        self.assertIn("savepoint", body)
        self.assertIn("nowdate()", body, "khong tao truoc ngay tuong lai")


class TestPatch(unittest.TestCase):
    def test_patch_dang_ky(self):
        src = _read(APP, "patches.txt")
        self.assertIn("ecentric_workspace.sla.patches.p015_phep_duyet_tre_resync", src)

    def test_patch_khong_xoa(self):
        src = _read(SLA, "patches", "p015_phep_duyet_tre_resync.py")
        compile(src, "p015", "exec")
        for bad in ("delete_doc", "frappe.delete", "DELETE FROM", ".delete("):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
