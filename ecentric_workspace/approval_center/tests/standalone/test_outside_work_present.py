# Copyright (c) 2026, eCentric and contributors
"""05/10/2026: Outside Work duyet xong -> Attendance "Present" cho ngay lam viec ben ngoai.
KHONG can bench: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_outside_work_present"""
import ast
import datetime as dt
import importlib
import io
import os
import sys
import types
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _mod():
    fr = types.ModuleType("frappe")
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda x: x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x))
    utils.nowdate = lambda: "2026-10-05"
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    sys.modules.pop("ecentric_workspace.approval_center.features.outside_work.application.attendance", None)
    return importlib.import_module("ecentric_workspace.approval_center.features.outside_work.application.attendance")


D = dt.date


class PlanDays(unittest.TestCase):
    def setUp(self):
        self.A = _mod()

    def test_mot_ngay_khong_co_cong(self):
        self.assertEqual(self.A.plan_days("2026-09-24", "2026-09-24", set(), set()), [D(2026, 9, 24)])

    def test_bo_cuoi_tuan_le_va_ngay_da_co_ban_ghi(self):
        days = self.A.plan_days("2026-09-01", "2026-09-08", {D(2026, 9, 2)}, {D(2026, 9, 3)})
        # 01 (T3), 04 (T6), 07 (T2), 08 (T3); 02 le, 03 da co, 05-06 cuoi tuan
        self.assertEqual(days, [D(2026, 9, 1), D(2026, 9, 4), D(2026, 9, 7), D(2026, 9, 8)])

    def test_chi_ngay_da_qua(self):
        self.assertEqual(self.A.plan_days("2026-10-07", "2026-10-09", set(), set(), before="2026-10-08"),
                         [D(2026, 10, 7)])

    def test_truoc_ngay_vao_lam_khong_tao(self):
        self.assertEqual(self.A.plan_days("2026-09-07", "2026-09-09", set(), set(), "2026-09-09"),
                         [D(2026, 9, 9)])


class DangKy(unittest.TestCase):
    def _src(self, *p):
        with io.open(os.path.join(APP, *p), encoding="utf-8") as fh:
            return fh.read()

    def test_engine_goi_handler_khi_duyet_xong(self):
        src = self._src("approval_center", "shared", "workflow", "transitions.py")
        node = [n.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_FULFILLMENT_HANDLERS" for t in n.targets)][0]
        m = {k.value: v.value for k, v in zip(node.keys, node.values)}
        self.assertEqual(m["EC Outside Work Request"],
                         "ecentric_workspace.approval_center.features.outside_work.application.attendance.on_final_approval")

    def test_handler_nuot_loi_va_khong_ghi_de(self):
        src = self._src("approval_center", "features", "outside_work", "application", "attendance.py")
        i = src.index("def on_final_approval")
        self.assertIn("except Exception", src[i:i + 500])
        self.assertIn('"docstatus": ("<", 2)', src)
        self.assertIn('if st != "Approved":', src)

    def test_job_hang_ngay_dang_ky(self):
        self.assertIn("ecentric_workspace.approval_center.features.outside_work.application.attendance.run_daily",
                      self._src("hooks.py"))
        src = self._src("approval_center", "features", "outside_work", "application", "attendance.py")
        self.assertIn("before=nowdate()", src)

    def test_sla_loai_tru_ngay_outside(self):
        src = self._src("sla", "infrastructure", "attendance_source.py")
        self.assertIn("def _outside_days(", src)
        self.assertIn("a.approval_status = 'Approved'", src)
        self.assertIn("action, closed_at, reason = ar.ACT_EXCLUDE, None, OUTSIDE_REASON", src)
        att = self._src("approval_center", "features", "outside_work", "application", "attendance.py")
        self.assertIn("att.sync_leave(emp.name, doc.start_date, end)", att)

    def test_patch_bu_phieu_cu(self):
        self.assertIn("approval_center.patches.p263_outside_work_present", self._src("patches.txt"))
        src = self._src("approval_center", "patches", "p263_outside_work_present.py")
        self.assertIn('backfill("2026-09-01")', src)
        for bad in ("delete_doc", "DELETE FROM", ".delete("):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
