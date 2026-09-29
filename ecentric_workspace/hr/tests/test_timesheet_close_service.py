"""Chot cong thang - luong nghiep vu (hr/timesheet_close/service.py) voi mot frappe gia.
KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_timesheet_close_service
"""
import datetime as dt
import importlib
import sys
import types
import unittest

NOW = [dt.datetime(2026, 10, 2, 10, 0)]


class Throw(Exception):
    pass


class Row(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class Doc(Row):
    def __init__(self, fr, data):
        super().__init__(data)
        object.__setattr__(self, "_fr", fr)
        object.__setattr__(self, "flags", types.SimpleNamespace())

    def insert(self, ignore_permissions=False):
        self["name"] = "%s-%s" % (self["period_month"], self["employee"])
        self._fr.rows[self["name"]] = Row(self)
        return self

    def save(self, ignore_permissions=False):
        self._fr.rows[self["name"]] = Row(self)


def _match(row, filters):
    for k, v in filters.items():
        val = row.get(k)
        if isinstance(v, tuple):
            op, arg = v
            if op == "in" and val not in arg:
                return False
            if op == "is" and arg == "not set" and val:
                return False
        elif val != v:
            return False
    return True


def make_frappe(emps, roles, pending=None):
    """emps: {emp: (name, user, reports_to)}; roles: {user: set}; pending: {emp: (appeal, late, {approver: n})}"""
    fr = types.ModuleType("frappe")
    fr.rows = {}
    pending = pending or {}
    DEPTS = {"D": Row(name="D", department_name="Service", manager_email="boss@x")}
    USERS = {"boss@x": 1, "vinh@x": 1, "hau@x": 1, "thu@x": 1, "ceo@x": 1, "cnb@x": 1}
    fr.PermissionError = Throw

    def throw(msg, exc=None):
        raise Throw(msg)
    fr.throw = throw

    def sql(q, params=(), as_dict=False):
        if "`tabHoliday`" in q:
            return []
        if "`tabHas Role`" in q:
            u, rs = params[0], params[1]
            return [(1,)] if roles.get(u, set()) & set(rs) else []
        if "left join `tabEmployee` m" in q:
            out = []
            for e, (_, _, rep) in emps.items():
                if rep and emps.get(rep) and emps[rep][1]:
                    out.append((e, emps[rep][1]))
            return out
        if "select name, employee_name, user_id, department" in q:
            return [Row(name=e, employee_name=v[0], user_id=v[1], department="D") for e, v in emps.items()]
        if "`tabAttendance Request`" in q:
            return [(e, pending[e][0]) for e in params[0] if e in pending and pending[e][0]]
        if "`tabAttendance`" in q:
            return [(e, pending[e][1]) for e in params[0] if e in pending and pending[e][1]]
        if "`tabLeave Application`" in q:
            return [(e, a, n) for e in params[0] if e in pending for a, n in pending[e][2].items()]
        raise AssertionError(q)

    def get_value(dt_, filters, field=None):
        if dt_ == "Company":
            return "HL"
        if dt_ == "Employee":
            for e, v in emps.items():
                if v[1] == filters.get("user_id"):
                    return e
            return None
        if dt_ == "Department":
            return DEPTS[filters][field] if filters in DEPTS else None
        if dt_ == "User":
            return USERS.get(filters)
        if dt_ == "EC Timesheet Close":
            for n, r in fr.rows.items():
                if _match(r, filters):
                    return n
        return None

    def set_value(dt_, name, field, value, update_modified=True):
        fr.rows[name][field] = value

    fr.db = types.SimpleNamespace(
        sql=sql, get_value=get_value, set_value=set_value,
        get_single_value=lambda *a: "EC",
        exists=lambda dt_, f: any(_match(r, f) for r in fr.rows.values()))
    DEPTS = {"D": Row(name="D", department_name="Service", manager_email="boss@x")}
    USERS = {"boss@x": 1, "vinh@x": 1, "hau@x": 1, "thu@x": 1, "ceo@x": 1, "cnb@x": 1}

    def get_all(dt_, filters=None, fields=None, **k):
        if dt_ == "User":
            return [Row(name=u, full_name=u.split("@")[0].title()) for u in USERS if u in filters["name"][1]]
        if dt_ == "Department":
            return list(DEPTS.values())
        return [Row(r) for r in fr.rows.values() if _match(r, filters or {})]
    fr.get_all = get_all
    fr.get_roles = lambda u: list(roles.get(u, set()))
    fr.sent = []
    ev = types.ModuleType("ecentric_workspace.notification_center.events")
    ev.publish_notification_event = lambda et, user, title, msg, **k: fr.sent.append((user, title, msg, k.get("dedupe_key")))
    sys.modules["ecentric_workspace.notification_center.events"] = ev
    fr.conf = {}

    def get_doc(a, b=None):
        if isinstance(a, dict):
            return Doc(fr, a)
        return Doc(fr, fr.rows[b])
    fr.get_doc = get_doc
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: NOW[0]
    utils.get_datetime = lambda x: x
    utils.getdate = lambda x: x
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    for m in ("ecentric_workspace.hr.timesheet_close.service", "ecentric_workspace.hr.timesheet_close.reminders"):
        sys.modules.pop(m, None)
    svc = importlib.import_module("ecentric_workspace.hr.timesheet_close.service")
    fr.rem = importlib.import_module("ecentric_workspace.hr.timesheet_close.reminders")
    return fr, svc


# Vinh quan ly Hau va Thu; CEO khong co quan ly; Vinh bao cao CEO.
EMPS = {"E-CEO": ("CEO", "ceo@x", None), "E-VINH": ("Vinh", "vinh@x", "E-CEO"),
        "E-HAU": ("Hau", "hau@x", "E-VINH"), "E-THU": ("Thu", "thu@x", "E-VINH")}
ROLES = {"cnb@x": {"EC CnB"}}


class ChotCong(unittest.TestCase):
    def setUp(self):
        NOW[0] = dt.datetime(2026, 10, 2, 10, 0)

    def test_sinh_dong_dung_leader_va_han(self):
        fr, S = make_frappe(EMPS, ROLES)
        self.assertEqual(S.ensure_rows("2026-09"), 4)
        self.assertEqual(S.ensure_rows("2026-09"), 0)   # chay lai khong sinh them
        r = fr.rows["2026-09-E-HAU"]
        self.assertEqual(r["lead_user"], "vinh@x")
        self.assertEqual(r["member_deadline"], dt.datetime(2026, 10, 2, 12, 0))
        self.assertIsNone(fr.rows["2026-09-E-CEO"]["lead_user"])

    def test_khong_sinh_ky_truoc_ngay_ap_dung(self):
        fr, S = make_frappe(EMPS, ROLES)
        self.assertEqual(S.ensure_rows("2026-08"), 0)

    def test_nhan_vien_tu_chot_roi_bi_khoa(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        self.assertEqual(S.close_self("hau@x")["status"], "Member Closed")
        self.assertTrue(S.is_locked("E-HAU", "2026-09"))
        self.assertFalse(S.is_locked("E-THU", "2026-09"))
        self.assertTrue(S.close_self("hau@x")["already"])

    def test_leader_bi_chan_khi_con_viec_cho_minh(self):
        fr, S = make_frappe(EMPS, ROLES, pending={"E-THU": (1, 0, {})})
        S.ensure_rows("2026-09")
        with self.assertRaises(Throw):
            S.close_team("vinh@x", "team")

    def test_don_o_buoc_nhan_su_khong_chan_leader(self):
        fr, S = make_frappe(EMPS, ROLES, pending={"E-THU": (0, 0, {"hr@x": 1})})
        S.ensure_rows("2026-09")
        st = S.get_state("vinh@x")
        g = st["groups"][0]
        self.assertTrue(g["can_close"])
        self.assertEqual(S.close_team("vinh@x", "team")["closed"], 2)

    def test_leader_chot_thay_nguoi_chua_chot(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        S.close_self("hau@x")
        NOW[0] = dt.datetime(2026, 10, 2, 14, 0)
        S.close_team("vinh@x", "team")
        hau, thu = fr.rows["2026-09-E-HAU"], fr.rows["2026-09-E-THU"]
        self.assertEqual((hau["status"], hau["close_mode"]), ("Closed", "Tu chot"))
        self.assertEqual((thu["status"], thu["close_mode"], thu["member_closed_by"]), ("Closed", "Leader chot thay", "vinh@x"))
        self.assertEqual(thu["team_closed_at"], dt.datetime(2026, 10, 2, 14, 0))

    def test_nguoi_khong_co_quan_ly_chi_cnb_hr_chot(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        with self.assertRaises(Throw):
            S.close_team("vinh@x", "nolead")
        st = S.get_state("cnb@x")
        self.assertEqual([g["key"] for g in st["groups"]], ["nolead"])
        S.close_team("cnb@x", "nolead")
        self.assertEqual(fr.rows["2026-09-E-CEO"]["close_mode"], "HR chot thay")

    def test_state_nhan_vien_qua_han(self):
        fr, S = make_frappe(EMPS, ROLES)
        NOW[0] = dt.datetime(2026, 10, 2, 12, 30)
        st = S.get_state("thu@x")
        self.assertTrue(st["active"] and st["show"])
        self.assertTrue(st["me"]["late"])
        self.assertEqual(st["member_deadline"], "2026-10-02 12:00")

    def test_chua_den_ky_thi_an(self):
        fr, S = make_frappe(EMPS, ROLES)
        NOW[0] = dt.datetime(2026, 9, 30, 10, 0)
        self.assertFalse(S.get_state("thu@x")["active"])
        with self.assertRaises(Throw):
            S.close_self("thu@x")



class TongQuanNhanSu(unittest.TestCase):
    """Tab 'Chot cong' tren /tong-quan#nhan-su va nut Nhac theo phong."""

    def setUp(self):
        NOW[0] = dt.datetime(2026, 10, 2, 10, 0)

    def test_chi_hr_cnb_xem_duoc(self):
        fr, S = make_frappe(EMPS, ROLES)
        self.assertTrue(S.can_overview("cnb@x"))
        self.assertFalse(S.can_overview("vinh@x"))

    def test_tien_do_theo_phong(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        S.close_self("hau@x")
        o = S.overview("cnb@x")
        self.assertTrue(o["active"])
        self.assertEqual(o["stats"], {"total": 4, "closed": 0, "self_closed": 1, "open": 3})
        d = o["departments"][0]
        self.assertEqual((d["label"], d["manager"], d["state"], d["total"]), ("Service", "Boss", "partial", 4))
        self.assertIn("Vinh", d["leads_pending"])

    def test_nhac_phong_gui_nhan_vien_leader_va_truong_phong(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        S.close_self("hau@x")
        r = fr.rem.remind_department("cnb@x", "D")
        to = sorted(u for u, *_ in fr.sent)
        # thu, vinh, ceo chua chot; vinh + ceo la leader con no; boss la truong phong. hau da chot -> khong nhan phan nhan vien
        self.assertEqual(to, ["boss@x", "ceo@x", "thu@x", "vinh@x"])
        self.assertEqual(r, {"members": 3, "leads": 3})
        msg_vinh = [m for u, t, m, k in fr.sent if u == "vinh@x"][0]
        self.assertIn("Bạn chưa chốt công", msg_vinh)
        self.assertIn("Team của bạn còn 2 người", msg_vinh)

    def test_nhan_vien_thuong_khong_bam_nhac_duoc(self):
        fr, S = make_frappe(EMPS, ROLES)
        S.ensure_rows("2026-09")
        with self.assertRaises(Throw):
            fr.rem.remind_department("vinh@x", "D")

    def test_chua_den_ky_thi_bao_ky_sap_toi(self):
        fr, S = make_frappe(EMPS, ROLES)
        NOW[0] = dt.datetime(2026, 9, 29, 10, 0)
        o = S.overview("cnb@x")
        self.assertFalse(o["active"])
        self.assertEqual((o["period"], o["opens"], o["member_deadline"]), ("2026-09", "2026-10-01", "2026-10-02 12:00"))

if __name__ == "__main__":
    unittest.main()
