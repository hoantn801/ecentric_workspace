# Copyright (c) 2026, eCentric and contributors
"""Lan quet mat tren may Hikvision -> `Employee Checkin` (+ `Attendance` Present).

MOT LUAT CHAM CONG, HAI CUA VAO. Cham tren web (Server Script `ec_hr_checkin`)
va quet mat tren may phai ra CUNG mot ket qua cho cung mot buoi sang:
    - lan cham DAU TIEN trong ngay la `IN`, cac lan sau la `OUT`;
    - lan dau <= gio chot cua ca (Shift Type.ec_checkin_cutoff, mac dinh 10:00),
      khong phai ngay nghi, khong co phep duyet, chua co Attendance
      -> tao Attendance `Present` (da submit);
    - tre hon gio chot thi chi ghi lan cham, khong tao Attendance (nhu web: 'Late').
`ec_hr_checkin` la Server Script, khong import duoc - SUA MOT BEN THI SUA CA HAI.

KHAC WEB O HAI CHO, deu vi su kien co the toi MUON (nut dong bo cuoi thang):
    - gio cham la gio QUET tren may, khong phai gio ERP nhan duoc;
    - mot lan quet SOM HON lan `IN` dang co thi gianh lay `IN`, lan cu thanh `OUT`.
Thang da chot cong (EC Timesheet Close) thi KHONG ghi them gi: chot la chot.

Chay lai bao nhieu lan cung vay: (nhan vien, gio quet) da co thi bo qua - day
cung la cach day-tuc-thi va dong-bo-cuoi-thang khong dem trung nhau.
"""
from ecentric_workspace.hr.face_device import constants as C
from ecentric_workspace.hr.face_device import mapper


def _hms(v):
    s = str(v or "").strip() or C.DEFAULT_CUTOFF
    return "0" + s if len(s) == 7 else s


class FaceCheckinService:
    def __init__(self, repo=None, tz_name=None, pass_minors=None):
        if repo is None:
            from ecentric_workspace.hr.face_device.repository import FaceCheckinRepository
            repo = FaceCheckinRepository()
        self.repo = repo
        self.tz_name = tz_name
        self.minors = tuple(pass_minors or C.DEFAULT_PASS_MINORS)
        self._emp = {}

    def execute(self, events, device_id):
        rep = {"received": len(events or []), "created": 0, "present": 0,
               "duplicate": 0, "closed": 0, "unknown": [], "bad_time": 0,
               "not_checkin": {}, "errors": 0}
        rows = []
        for ev in (events or [])[:C.MAX_EVENTS_PER_CALL]:
            if not mapper.is_pass(ev, self.minors):
                k = "%s/%s" % (ev.get("major"), ev.get("minor"))
                rep["not_checkin"][k] = rep["not_checkin"].get(k, 0) + 1
                continue
            t = mapper.to_local(ev.get("time"), self.tz_name)
            if t is None:
                rep["bad_time"] += 1
                continue
            rows.append((t, ev["employee_no"]))
        for i, (t, no) in enumerate(sorted(rows)):
            sp = "ec_face_%d" % i
            self.repo.savepoint(sp)
            try:
                self._one(t, no, device_id, rep)
            except Exception:
                self.repo.rollback(sp)
                rep["errors"] += 1
                self.repo.log_error("face_checkin %s %s" % (no, t))
        if rep["unknown"]:
            self.repo.log_once("unknown:" + ",".join(rep["unknown"]),
                               "face_checkin: ma tren may chua gan nhan vien",
                               ", ".join(rep["unknown"]))
        return rep

    def _employee(self, no):
        if no not in self._emp:
            emp = self.repo.employee_by_device_no(no)
            if not emp and no.isdigit() and len(no.lstrip("0") or "0") <= C.EMPLOYEE_DIGITS:
                # Quy uoc mac dinh: ma tren may = so cua ma nhan vien (70 / 00070
                # -> HR-EMP-00070), chi ap cho ho so CHUA dien Attendance Device ID.
                name = C.EMPLOYEE_SERIES + no.lstrip("0").zfill(C.EMPLOYEE_DIGITS)
                emp = self.repo.employee_by_name_unmapped(name)
            self._emp[no] = emp
        return self._emp[no]

    def _one(self, t, no, device_id, rep):
        emp = self._employee(no)
        if not emp:
            if no not in rep["unknown"]:
                rep["unknown"].append(no)
            return
        if self.repo.month_closed(emp["name"], t.strftime("%Y-%m")):
            rep["closed"] += 1
            return
        if self.repo.checkin_exists(emp["name"], t):
            rep["duplicate"] += 1
            return
        first = self.repo.first_in(emp["name"], t.date())
        is_in = not first or t < first["time"]
        shift = emp.get("default_shift") or C.DEFAULT_SHIFT
        self.repo.insert_checkin(emp["name"], t, C.LOG_IN if is_in else C.LOG_OUT,
                                 shift, device_id)
        rep["created"] += 1
        if not is_in:
            return
        if first:
            self.repo.set_log_type(first["name"], C.LOG_OUT)
        if self._mark_present(emp, t, shift):
            rep["present"] += 1

    def _mark_present(self, emp, t, shift):
        if t.strftime("%H:%M:%S") > _hms(self.repo.shift_cutoff(shift)):
            return False
        day = t.date()
        if (self.repo.is_holiday(emp, day) or self.repo.on_leave(emp["name"], day)
                or self.repo.attendance_exists(emp["name"], day)):
            return False
        self.repo.insert_present(emp, day, shift)
        return True
