# Copyright (c) 2026, eCentric and contributors
"""'Mac dinh du cong' (01/10/2026): noi day giua full_cong va SLA / nhac / chot cong."""
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "..")


def _read(*p):
    with io.open(os.path.join(APP, *p), encoding="utf-8") as fh:
        return fh.read()


class TestNoiDay(unittest.TestCase):
    def test_sla_bo_nguoi_du_cong(self):
        src = _read("sla", "infrastructure", "attendance_source.py")
        self.assertIn("full_cong.employees()", src)
        self.assertIn("if rows and rows[0][\"name\"] in _full_cong()", src)

    def test_khong_nhac_cham_cong(self):
        src = _read("hr", "checkin_reminder.py")
        i = src.index("def _should_skip(")
        self.assertIn("full_cong.is_full_cong", src[i:i + 600])

    def test_khong_sinh_dong_chot_cong_moi(self):
        src = _read("hr", "timesheet_close", "service.py")
        self.assertIn("if e.name in no_close and e.name not in have", src)

    def test_job_va_patch_dang_ky(self):
        self.assertIn("ecentric_workspace.hr.full_cong.run_daily", _read("hooks.py"))
        self.assertIn("ecentric_workspace.hr.patches.p004_full_cong", _read("patches.txt"))

    def test_khong_ghi_de_ngay_da_co_va_bo_cuoi_tuan(self):
        src = _read("hr", "full_cong.py")
        self.assertIn("if d in have:", src)
        self.assertIn("d.weekday() not in WORKDAYS or d in hol", src)
        self.assertIn("rollback(save_point=sp)", src)

    def test_patch_khong_xoa(self):
        src = _read("hr", "patches", "p004_full_cong.py")
        for bad in ("delete_doc", "DELETE FROM", ".delete("):
            self.assertNotIn(bad, src)


class TestDoiQuanLy(unittest.TestCase):
    def test_hook_dang_ky_va_nuot_loi(self):
        self.assertIn("ecentric_workspace.hr.reports_to_sync.on_employee_update", _read("hooks.py"))
        src = _read("hr", "reports_to_sync.py")
        self.assertIn('has_value_changed("reports_to")', src)
        self.assertIn('"status": ("!=", "Closed")', src)
        self.assertIn("except Exception", src)


if __name__ == "__main__":
    unittest.main()
