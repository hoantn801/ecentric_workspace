# Copyright (c) 2026, eCentric and contributors
"""'Mac dinh du cong' - phan 02/10/2026: tick la ghi cong / tu chot ngay, khong canh bao thieu
tai khoan. frappe gia, KHONG can bench:
python -m unittest ecentric_workspace.hr.tests.test_full_cong_hook"""
import datetime as dt
import importlib
import sys
import types
import unittest


class Row(dict):
    __getattr__ = dict.get


def _match(row, filters):
    for k, v in (filters or {}).items():
        val = row.get(k)
        if isinstance(v, tuple):
            op, arg = v
            if op == "in" and val not in arg:
                return False
            if op == "!=" and val == arg:
                return False
        elif val != v:
            return False
    return True


def make(emps, closes, obligations=()):
    fr = types.ModuleType("frappe")
    fr.logs, fr.msgs = [], []
    tables = {"Employee": emps, "EC Timesheet Close": closes, "EC SLA Obligation": list(obligations)}

    def get_all(dt_, filters=None, fields=None, pluck=None, **k):
        rows = [Row(r) for r in tables[dt_] if _match(r, filters)]
        return [r[pluck] for r in rows] if pluck else rows

    def set_value(dt_, name, field, value=None, update_modified=True):
        vals = field if isinstance(field, dict) else {field: value}
        for r in tables[dt_]:
            if r["name"] == name:
                r.update(vals)
    fr.get_all = get_all
    fr.db = types.SimpleNamespace(set_value=set_value, has_column=lambda *a: True,
                                  get_value=lambda *a, **k: None)
    fr.log_error = lambda *a, **k: fr.logs.append(k.get("title") or (a[1] if len(a) > 1 else a))
    fr.msgprint = lambda *a, **k: fr.msgs.append(a)
    fr.flags = types.SimpleNamespace()
    fr._ = lambda s: s
    fr.whitelist = lambda **k: (lambda f: f)
    fr.conf = {}
    fr.get_traceback = lambda: "tb"
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: dt.datetime(2026, 10, 2, 11, 30)
    utils.getdate = lambda x: x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x))
    utils.nowdate = lambda: "2026-10-02"
    utils.escape_html = lambda s: s
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    ev = types.ModuleType("ecentric_workspace.notification_center.events")
    ev.publish_notification_event = lambda **k: None
    sys.modules["ecentric_workspace.notification_center.events"] = ev
    for m in ("ecentric_workspace.hr.full_cong", "ecentric_workspace.hr.employee_guard",
              "ecentric_workspace.hr.timesheet_close.rules"):
        sys.modules.pop(m, None)
    return fr, importlib.import_module("ecentric_workspace.hr.full_cong")


class Doc(Row):
    def __init__(self, data, before=None):
        super().__init__(data)
        self._before = before

    def get_doc_before_save(self):
        return self._before


EMPS = [{"name": "E-LINH", "status": "Active", "ec_full_cong": 1, "user_id": None},
        {"name": "E-TUAN", "status": "Active", "ec_full_cong": 1, "user_id": "tuan@x"},
        {"name": "E-HAU", "status": "Active", "ec_full_cong": 0, "user_id": "hau@x"}]


def closes():
    return [{"name": "C1", "employee": "E-LINH", "status": "Open"},
            {"name": "C2", "employee": "E-TUAN", "status": "Member Closed"},
            {"name": "C3", "employee": "E-HAU", "status": "Open"},
            {"name": "C4", "employee": "E-TUAN", "status": "Closed", "close_mode": "Tu chot"}]


class TuChot(unittest.TestCase):
    def test_chi_dong_nguoi_du_cong_chua_chot(self):
        rows = closes()
        fr, FC = make([dict(e) for e in EMPS], rows)
        self.assertEqual(FC.close_rows(), 2)
        by = {r["name"]: r for r in rows}
        self.assertEqual((by["C1"]["status"], by["C1"]["close_mode"], by["C1"]["member_closed_by"]),
                         ("Closed", "HR chot thay", "Administrator"))
        # da tu chot thi giu nguyen cach chot, chi khoa team
        self.assertEqual((by["C2"]["status"], by["C2"].get("close_mode")), ("Closed", None))
        self.assertEqual(by["C3"]["status"], "Open")
        self.assertEqual(by["C4"]["close_mode"], "Tu chot")

    def test_only_gioi_han_mot_nguoi(self):
        rows = closes()
        fr, FC = make([dict(e) for e in EMPS], rows)
        self.assertEqual(FC.close_rows(only={"E-LINH"}), 1)
        self.assertEqual({r["name"]: r["status"] for r in rows}["C2"], "Member Closed")


class HookTick(unittest.TestCase):
    def _run(self, doc, obligations=()):
        rows = closes()
        obs = [dict(o) for o in obligations]
        fr, FC = make([dict(e) for e in EMPS], rows, obs)
        calls = []
        FC.mark_range = lambda s, e, only=None: calls.append((str(s), str(e), only))
        FC.on_employee_update(doc)
        return fr, rows, obs, calls

    def test_vua_tick_thi_ghi_cong_huy_sla_tu_chot(self):
        doc = Doc({"name": "E-TUAN", "status": "Active", "ec_full_cong": 1, "user_id": "tuan@x"},
                  before=Row({"ec_full_cong": 0}))
        ob = [{"name": "O1", "obligation_type": "ATTENDANCE_DAY", "owner_user": "tuan@x", "status": "Open"},
              {"name": "O2", "obligation_type": "APPROVAL", "owner_user": "tuan@x", "status": "Open"}]
        fr, rows, obs, calls = self._run(doc, ob)
        self.assertEqual(calls, [("2026-09-01", "2026-10-02", {"E-TUAN"})])
        self.assertEqual({r["name"]: r["status"] for r in rows}["C2"], "Closed")
        self.assertEqual({o["name"]: o["status"] for o in obs}, {"O1": "Cancelled", "O2": "Open"})

    def test_tao_moi_da_tick_cung_chay(self):
        doc = Doc({"name": "E-LINH", "status": "Active", "ec_full_cong": 1}, before=None)
        fr, rows, obs, calls = self._run(doc)
        self.assertEqual(calls[0][2], {"E-LINH"})

    def test_da_tick_tu_truoc_thi_khong_lam_lai(self):
        doc = Doc({"name": "E-TUAN", "status": "Active", "ec_full_cong": 1}, before=Row({"ec_full_cong": 1}))
        fr, rows, obs, calls = self._run(doc)
        self.assertEqual(calls, [])

    def test_khong_tick_thi_bo_qua_va_khong_bao_gio_nem_loi(self):
        fr, rows, obs, calls = self._run(Doc({"name": "E-HAU", "status": "Active", "ec_full_cong": 0}))
        self.assertEqual(calls, [])
        rows = closes()
        fr, FC = make([dict(e) for e in EMPS], rows)

        def boom(*a, **k):
            raise RuntimeError("x")
        FC.mark_range = boom
        FC.on_employee_update(Doc({"name": "E-TUAN", "status": "Active", "ec_full_cong": 1}))
        self.assertTrue(fr.logs)


class KhongCanhBaoThieuTaiKhoan(unittest.TestCase):
    def test_nguoi_du_cong_khong_bi_canh_bao(self):
        fr, FC = make([dict(e) for e in EMPS], closes())
        G = importlib.import_module("ecentric_workspace.hr.employee_guard")
        G.autofill_user_id(Row({"name": "E-LINH", "status": "Active", "ec_full_cong": 1}))
        self.assertEqual(fr.msgs, [])
        G.autofill_user_id(Row({"name": "E-X", "status": "Active", "ec_full_cong": 0}))
        self.assertEqual(len(fr.msgs), 1)

    def test_ban_quet_sang_bo_nguoi_du_cong(self):
        emps = [dict(e, employee_name=e["name"], date_of_joining="2023-01-01") for e in EMPS]
        fr, FC = make(emps, closes())
        fr.utils.add_days = lambda d, n: "2026-10-04"
        G = importlib.import_module("ecentric_workspace.hr.employee_guard")
        self.assertEqual([r["name"] for r in G._offenders()], [])


if __name__ == "__main__":
    unittest.main()
