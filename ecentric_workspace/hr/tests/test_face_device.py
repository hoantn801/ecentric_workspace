# Copyright (c) 2026, eCentric and contributors
"""May cham cong khuon mat Hikvision -> Employee Checkin (hr/face_device).

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_face_device
"""
import datetime as dt
import json
import os
import unittest

from ecentric_workspace.hr.face_device import constants as C
from ecentric_workspace.hr.face_device import mapper
from ecentric_workspace.hr.face_device.service import FaceCheckinService

TZ = "Asia/Ho_Chi_Minh"
D = dt.datetime


def ev(no, t, minor=75, major=5):
    return {"employee_no": no, "time": t, "major": major, "minor": minor, "serial": 1}


class FakeRepo:
    def __init__(self):
        self.emps = {"HR-EMP-00070": {"name": "HR-EMP-00070", "employee_name": "Dong",
                                      "default_shift": None, "holiday_list": "HL",
                                      "company": "eCentric", "device_no": ""},
                     "HR-EMP-00074": {"name": "HR-EMP-00074", "employee_name": "Thu",
                                      "default_shift": "EC Standard 9-18",
                                      "holiday_list": "HL", "company": "eCentric",
                                      "device_no": "1074"}}
        self.checkins = []      # dict(name, employee, time, log_type, device_id)
        self.attendance = set()
        self.holidays = set()
        self.leaves = set()
        self.closed = set()
        self.logged = []
        self.rolled_back = []
        self.boom = set()

    def employee_by_device_no(self, no):
        for e in self.emps.values():
            if e["device_no"] == no:
                return e
        return None

    def employee_by_name_unmapped(self, name):
        e = self.emps.get(name)
        return e if e and not e["device_no"] else None

    def checkin_exists(self, emp, t):
        return any(c["employee"] == emp and c["time"] == t for c in self.checkins)

    def first_in(self, emp, day):
        rows = sorted((c for c in self.checkins if c["employee"] == emp
                       and c["log_type"] == "IN" and c["time"].date() == day),
                      key=lambda c: c["time"])
        return rows[0] if rows else None

    def insert_checkin(self, emp, t, log_type, shift, device_id):
        if emp in self.boom:
            raise RuntimeError("boom")
        name = "CI-%d" % (len(self.checkins) + 1)
        self.checkins.append({"name": name, "employee": emp, "time": t,
                              "log_type": log_type, "shift": shift, "device_id": device_id})
        return name

    def set_log_type(self, name, lt):
        for c in self.checkins:
            if c["name"] == name:
                c["log_type"] = lt

    def month_closed(self, emp, pm):
        return (emp, pm) in self.closed

    def shift_cutoff(self, shift):
        return "10:00:00"

    def is_holiday(self, emp, day):
        return day in self.holidays

    def on_leave(self, emp, day):
        return (emp, day) in self.leaves

    def attendance_exists(self, emp, day):
        return (emp, day) in self.attendance

    def insert_present(self, emp, day, shift):
        self.attendance.add((emp["name"], day))

    def savepoint(self, name):
        pass

    def rollback(self, name):
        self.rolled_back.append(name)

    def log_error(self, title):
        self.logged.append(title)

    def log_once(self, key, title, message):
        self.logged.append(title + ": " + message)


class TestService(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()
        self.svc = FaceCheckinService(self.repo, tz_name=TZ)

    def run_(self, events, device="HIK-VP"):
        return FaceCheckinService(self.repo, tz_name=TZ).execute(events, device)

    def lt(self, emp):
        return [(c["time"].strftime("%H:%M"), c["log_type"]) for c in
                sorted(self.repo.checkins, key=lambda c: c["time"]) if c["employee"] == emp]

    def test_quet_dau_ngay_truoc_gio_chot_la_IN_va_co_cong(self):
        rep = self.run_([ev("1074", "2026-10-12T08:45:12+07:00")])
        self.assertEqual((rep["created"], rep["present"]), (1, 1))
        self.assertEqual(self.lt("HR-EMP-00074"), [("08:45", "IN")])
        self.assertIn(("HR-EMP-00074", dt.date(2026, 10, 12)), self.repo.attendance)
        self.assertEqual(self.repo.checkins[0]["device_id"], "HIK-VP")

    def test_lan_sau_trong_ngay_la_OUT(self):
        self.run_([ev("1074", "2026-10-12T08:45:00+07:00"), ev("1074", "2026-10-12T18:05:00+07:00")])
        self.assertEqual(self.lt("HR-EMP-00074"), [("08:45", "IN"), ("18:05", "OUT")])

    def test_day_tuc_thi_va_dong_bo_cuoi_thang_khong_trung(self):
        self.run_([ev("1074", "2026-10-12T08:45:00+07:00")])
        rep = self.run_([ev("1074", "2026-10-12T08:45:00+07:00")], "HIK-sync")
        self.assertEqual((rep["created"], rep["duplicate"]), (0, 1))
        self.assertEqual(len(self.repo.checkins), 1)

    def test_tre_hon_gio_chot_chi_ghi_lan_cham(self):
        rep = self.run_([ev("1074", "2026-10-12T10:00:01+07:00")])
        self.assertEqual((rep["created"], rep["present"]), (1, 0))
        self.assertFalse(self.repo.attendance)

    def test_dung_gio_chot_van_tinh_cong(self):
        self.assertEqual(self.run_([ev("1074", "2026-10-12T10:00:00+07:00")])["present"], 1)

    def test_quet_som_hon_toi_muon_gianh_IN(self):
        # Push lo mat lan 08:40, chi nhan lan 10:30 (tre). Cuoi thang dong bo bu lan 08:40.
        self.run_([ev("1074", "2026-10-12T10:30:00+07:00")])
        self.assertFalse(self.repo.attendance)
        rep = self.run_([ev("1074", "2026-10-12T08:40:00+07:00")])
        self.assertEqual(self.lt("HR-EMP-00074"), [("08:40", "IN"), ("10:30", "OUT")])
        self.assertEqual(rep["present"], 1)

    def test_ngay_nghi_phep_hay_da_co_cong_thi_khong_tao_them(self):
        day = dt.date(2026, 10, 12)
        self.repo.holidays.add(day)
        self.assertEqual(self.run_([ev("1074", "2026-10-12T08:00:00+07:00")])["present"], 0)
        self.repo.holidays.clear()
        self.repo.leaves.add(("HR-EMP-00074", dt.date(2026, 10, 13)))
        self.assertEqual(self.run_([ev("1074", "2026-10-13T08:00:00+07:00")])["present"], 0)
        self.repo.attendance.add(("HR-EMP-00074", dt.date(2026, 10, 14)))
        self.assertEqual(self.run_([ev("1074", "2026-10-14T08:00:00+07:00")])["present"], 0)

    def test_thang_da_chot_thi_khong_ghi(self):
        self.repo.closed.add(("HR-EMP-00074", "2026-09"))
        rep = self.run_([ev("1074", "2026-09-30T08:00:00+07:00")])
        self.assertEqual((rep["closed"], rep["created"]), (1, 0))
        self.assertFalse(self.repo.checkins)

    def test_ma_so_tren_may_tu_khop_ma_nhan_vien(self):
        for no in ("70", "00070"):
            self.repo.checkins.clear()
            rep = FaceCheckinService(self.repo, tz_name=TZ).execute(
                [ev(no, "2026-10-12T08:00:00+07:00")], "HIK")
            self.assertEqual(rep["created"], 1, no)
            self.assertEqual(self.repo.checkins[0]["employee"], "HR-EMP-00070")

    def test_ho_so_da_co_device_id_thi_khong_khop_theo_so(self):
        # HR-EMP-00074 dang dung ma 1074 -> "74" KHONG duoc tu khop vao Thu.
        rep = self.run_([ev("74", "2026-10-12T08:00:00+07:00")])
        self.assertEqual(rep["unknown"], ["74"])
        self.assertFalse(self.repo.checkins)
        self.assertTrue(any("74" in m for m in self.repo.logged))

    def test_khong_phai_xac_thuc_thanh_cong_thi_bo(self):
        rep = self.run_([ev("1074", "2026-10-12T08:00:00+07:00", minor=76),
                         ev("1074", "2026-10-12T08:00:00+07:00", major=3, minor=75),
                         ev("", "2026-10-12T08:00:00+07:00")])
        self.assertEqual(rep["created"], 0)
        self.assertEqual(rep["not_checkin"], {"5/76": 1, "3/75": 1, "5/75": 1})

    def test_doi_mui_gio_ve_gio_he_thong(self):
        self.run_([ev("1074", "2026-10-12T01:45:00Z")])
        self.assertEqual(self.lt("HR-EMP-00074"), [("08:45", "IN")])

    def test_mot_dong_loi_khong_keo_ca_lo(self):
        self.repo.boom.add("HR-EMP-00070")
        rep = self.run_([ev("70", "2026-10-12T08:00:00+07:00"),
                         ev("1074", "2026-10-12T08:01:00+07:00")])
        self.assertEqual((rep["errors"], rep["created"]), (1, 1))
        self.assertEqual(len(self.repo.rolled_back), 1)

    def test_ma_minor_cau_hinh_duoc(self):
        rep = FaceCheckinService(self.repo, tz_name=TZ, pass_minors=[104]).execute(
            [ev("1074", "2026-10-12T08:00:00+07:00", minor=104)], "HIK")
        self.assertEqual(rep["created"], 1)


class TestMapper(unittest.TestCase):
    ACE = {"majorEventType": 5, "subEventType": 75, "employeeNoString": "1074",
           "name": "Thu", "serialNo": 812, "currentVerifyMode": "cardOrFaceOrFp"}

    def test_multipart_event_log(self):
        form = {"event_log": json.dumps({"ipAddress": "192.168.1.50",
                                         "dateTime": "2026-10-12T08:45:12+07:00",
                                         "eventType": "AccessControllerEvent",
                                         "AccessControllerEvent": self.ACE})}
        out = mapper.from_push(form)
        self.assertEqual(out, [{"employee_no": "1074", "time": "2026-10-12T08:45:12+07:00",
                                "major": 5, "minor": 75, "serial": 812}])

    def test_body_json_da_parse_vao_form(self):
        form = {"dateTime": "2026-10-12T08:45:12+07:00", "AccessControllerEvent": self.ACE}
        self.assertEqual(mapper.from_push(form)[0]["employee_no"], "1074")

    def test_body_xml(self):
        raw = ('<EventNotificationAlert version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">'
               '<dateTime>2026-10-12T08:45:12+07:00</dateTime><eventType>AccessControllerEvent</eventType>'
               '<AccessControllerEvent><majorEventType>5</majorEventType><subEventType>75</subEventType>'
               '<employeeNoString>1074</employeeNoString></AccessControllerEvent></EventNotificationAlert>')
        out = mapper.from_push({}, raw)
        self.assertEqual((out[0]["employee_no"], out[0]["minor"], out[0]["time"]),
                         ("1074", 75, "2026-10-12T08:45:12+07:00"))

    def test_heartbeat_khong_phai_su_kien(self):
        self.assertEqual(mapper.from_push({"eventType": "heartBeat",
                                           "dateTime": "2026-10-12T08:45:12+07:00"}), [])
        self.assertEqual(mapper.from_push({}, ""), [])

    def test_infolist_cua_acsevent(self):
        items = [{"major": 5, "minor": 75, "time": "2026-10-12T08:45:12+07:00",
                  "employeeNoString": "1074", "serialNo": 9},
                 {"major": 2, "minor": 39, "time": "2026-10-12T08:46:00+07:00"}]
        out = mapper.from_sync(items)
        self.assertEqual([o["employee_no"] for o in out], ["1074", ""])

    def test_to_local(self):
        self.assertEqual(mapper.to_local("2026-10-12T08:45:12+07:00", TZ), D(2026, 10, 12, 8, 45, 12))
        self.assertEqual(mapper.to_local("2026-10-12 08:45:12", TZ), D(2026, 10, 12, 8, 45, 12))
        self.assertIsNone(mapper.to_local("hom qua", TZ))
        self.assertIsNone(mapper.to_local("", TZ))


class TestCungLuatVoiChamCongWeb(unittest.TestCase):
    """`ec_hr_checkin` (Server Script) va service nay phai cung ca + gio chot mac dinh."""

    def test_mac_dinh_khop_server_script(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        with open(os.path.join(root, "fixtures", "server_script.json"), encoding="utf-8") as fh:
            src = [r for r in json.load(fh) if r["name"] == "ec_hr_checkin"][0]["script"]
        self.assertIn("'%s'" % C.DEFAULT_SHIFT, src)
        self.assertIn("cutoff = '%s'" % C.DEFAULT_CUTOFF, src)
        self.assertIn("log_type': 'IN'", src)


if __name__ == "__main__":
    unittest.main()
