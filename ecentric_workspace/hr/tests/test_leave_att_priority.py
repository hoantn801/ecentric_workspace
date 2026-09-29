# Copyright (c) 2026, eCentric and contributors
"""Don nghi phai duyet / tu choi duoc ca khi ngay nghi da co cham cong 'Present'.

VI SAO CO FILE NAY
    29/09: Vinh bam duyet don nghi nua ngay cua Hau (HR-LAP-2026-00070) ma don khong
    nhuc nhich. Hau xin nghi buoi sang, chieu van di lam va bam cham cong ->
    ec_hr_checkin tao Attendance 'Present'. HRMS Leave Application.validate_attendance
    tu choi MOI lan luu don khi ngay nghi co Attendance Present/WFH (half_day_status
    != 'Absent'): ca duyet lan tu choi. 6/12 don Open ket vi dung ly do nay.
    Hoan chot: PHEP UU TIEN HON CHAM CONG (ec-lv-att-priority-v1).

TEST CHAY TREN CHINH VAN BAN SCRIPT TRONG FIXTURE, voi mot frappe gia mo phong dung
hai cho cua HRMS lien quan: validate_attendance (luc save/submit) va
create_or_update_attendance (on_submit khi Approved).
KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_leave_att_priority
"""
import json
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "..", "fixtures", "server_script.json")


def _script():
    with open(FIX, encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r["name"] == "ec_hr_leave_decide"][0]["script"]


class Throw(Exception):
    pass


class FakeDB:
    def __init__(self, att):
        self.att = att  # name -> dict

    def _blocking(self, emp, d1, d2):
        return [a for a in self.att.values()
                if a["employee"] == emp and d1 <= a["date"] <= d2 and a["docstatus"] == 1
                and a["status"] in ("Present", "Work From Home") and (a["half_day_status"] or "") != "Absent"]

    def sql(self, q, params=()):
        if "`tabHas Role`" in q and "HR Manager" in q and "limit 1" in q:
            return [("hr@x",)]
        if "`tabHas Role`" in q:
            return []  # nguoi duyet khong phai HR
        if "`tabEmployee` mm" in q:
            return []
        if "from `tabAttendance`" in q:
            return [(a["name"], a["half_day_status"]) for a in self._blocking(*params)]
        if "`tabToDo`" in q:
            return []
        raise AssertionError("sql la: " + q)

    def get_value(self, dt, name, field):
        if dt == "Employee":
            return {"reports_to": "EMP-MGR", "user_id": "vinh@x" if name == "EMP-MGR" else "hau@x"}[field]
        if dt == "Attendance":
            return self.att[name][field]
        raise AssertionError(dt)

    def set_value(self, dt, name, field, value, update_modified=True):
        assert dt == "Attendance"
        self.att[name][field] = value


class FakeLeave(dict):
    """Mo phong Leave Application cua HRMS o dung hai diem gay ket."""

    def __init__(self, db, **kw):
        super().__init__(**kw)
        self.db = db
        self.flags = types.SimpleNamespace()
        self.docstatus = 0

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        if k in ("db", "flags", "docstatus"):
            object.__setattr__(self, k, v)
        else:
            self[k] = v

    def _validate(self):
        if self.db._blocking(self.employee, self.from_date, self.to_date):
            raise Throw("Attendance for employee %s is already marked" % self.employee)

    def save(self, ignore_permissions=False):
        self._validate()

    def submit(self):
        self._validate()
        self.docstatus = 1
        if self.status == "Approved":  # create_or_update_attendance cua HRMS
            for a in self.db.att.values():
                if a["employee"] == self.employee and self.from_date <= a["date"] <= self.to_date:
                    half = self.half_day and a["date"] == self.half_day_date
                    a.update(status="Half Day" if half else "On Leave", leave_application=self.name,
                             half_day_status="Present" if half else None)

    def add_comment(self, *a):
        pass


def run(action, stage="", half_day=1, att_status="Present"):
    att = {"ATT-1": {"name": "ATT-1", "employee": "EMP-HAU", "date": "2026-09-29", "docstatus": 1,
                     "status": att_status, "half_day_status": None, "leave_application": None}}
    db = FakeDB(att)
    la = FakeLeave(db, name="LAP-70", employee="EMP-HAU", employee_name="Hau", from_date="2026-09-29",
                   to_date="2026-09-29", half_day=half_day, half_day_date="2026-09-29" if half_day else None,
                   status="Open", ec_approval_stage=stage, leave_type="Annual Leave", total_leave_days=0.5,
                   leave_approver="vinh@x")
    fr = types.SimpleNamespace()
    fr.session = types.SimpleNamespace(user="vinh@x")
    fr.form_dict = {"name": "LAP-70", "action": action}
    fr.response = {}
    fr.db = db

    def throw(msg):
        raise Throw(msg)
    fr.throw = throw
    fr.get_doc = lambda *a: la if a and a[0] == "Leave Application" else types.SimpleNamespace(
        flags=types.SimpleNamespace(), insert=lambda **k: None)
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda: ""
    exec(compile(_script(), "ec_hr_leave_decide", "exec"), {"frappe": fr})
    return la, att["ATT-1"], fr.response


class TestPhepUuTienHonChamCong(unittest.TestCase):
    def test_duyet_nua_ngay_khi_da_cham_cong(self):
        la, att, resp = run("approve")
        self.assertEqual(la.status, "Approved")
        self.assertEqual(la.docstatus, 1)
        self.assertEqual((att["status"], att["half_day_status"], att["leave_application"]),
                         ("Half Day", "Present", "LAP-70"))
        self.assertEqual(resp["message"]["status"], "Approved")

    def test_duyet_ca_ngay_khi_da_cham_cong_thi_phep_thang(self):
        la, att, _ = run("approve", half_day=0)
        self.assertEqual(la.status, "Approved")
        self.assertEqual((att["status"], att["leave_application"]), ("On Leave", "LAP-70"))

    def test_tu_choi_duoc_va_cham_cong_giu_nguyen(self):
        la, att, _ = run("reject")
        self.assertEqual(la.status, "Rejected")
        self.assertEqual((att["status"], att["half_day_status"], att["leave_application"]),
                         ("Present", None, None))

    def test_buoc_lead_luu_duoc_va_cham_cong_giu_nguyen(self):
        la, att, resp = run("approve", stage="lead")
        self.assertEqual(la.ec_approval_stage, "hr")
        self.assertEqual(la.docstatus, 0)
        self.assertEqual((att["status"], att["half_day_status"]), ("Present", None))

    def test_khong_dung_vao_ngay_khong_co_cham_cong_di_lam(self):
        la, att, _ = run("approve", att_status="Absent")
        self.assertEqual(la.status, "Approved")
        self.assertEqual(att["status"], "Half Day")


if __name__ == "__main__":
    unittest.main()
