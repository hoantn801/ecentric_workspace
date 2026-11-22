# Copyright (c) 2026, eCentric and contributors
"""Khao sat ca nhan theo moc (23/11/2026, HR Dot 2) - chay khong can bench.

    python -m pytest ecentric_workspace/surveys/tests/test_ca_nhan.py

Kiem:
  * moc 7/30/45 (thu viec) va 30/60/75 (thuc tap), doi ngay nghi, moc cuoi keo truoc ngay tao
    nhap danh gia (D-21), chi giao MOT moc dang mo (khong ban ca ba mot luc);
  * giao_khao_sat: chu ky on dinh (Agent C goi), chong giao trung, han tinh ngay lam viec, thieu mau
    -> ok False khong nem loi, mau chua mo;
  * job nhac: MOT lan, tu 1 ngay lam viec truoc han, khong nhac nguoi da nop / nguoi dang nghi,
    ghi reminded_at; NV khong con Active -> huy lan giao;
  * quyen xem: HR / C&B xem du; LM chi cap duoi TRUC TIEP va bi an cau "chi HR"; khao sat nghi
    viec (nguoi xem chi HR) -> LM khong xem; nguoi ngoai khong xem.
"""
import datetime as dt
import inspect
import json
import sys
import types
import unittest


def _install_fake_frappe():
    """frappe gia CHI de import infrastructure (service nhan repo gia qua tham so)."""
    if "frappe" in sys.modules:
        return
    fr = types.ModuleType("frappe")
    fr.whitelist = lambda *a, **k: (lambda f: f)
    utils = types.ModuleType("frappe.utils")
    for n in ("get_datetime", "now_datetime", "getdate", "nowdate", "strip_html", "add_days"):
        setattr(utils, n, lambda *a, **k: None)
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils


_install_fake_frappe()

from ecentric_workspace.surveys import constants as C  # noqa: E402
from ecentric_workspace.surveys.application import access, ca_nhan  # noqa: E402
from ecentric_workspace.surveys.domain import ca_nhan as rule  # noqa: E402
from ecentric_workspace.surveys.domain import moc  # noqa: E402
from ecentric_workspace.surveys.domain.errors import SurveyPermissionError  # noqa: E402

D = dt.date


class FakeRepo:
    def __init__(self, today=D(2026, 11, 23)):
        self._today = today
        self.surveys = {}
        self.assigns = {}
        self.parts = {}          # (survey, user) -> participant
        self.responses = {}
        self.notified = []
        self.errors = []
        self.emps = {}           # user -> {name, status, reports_to_user}
        self.holidays = set()
        self.nghi = set()
        self._seq = 0

    # survey
    def survey_by_ma_mau(self, ma):
        return next((s for s in self.surveys.values() if s.get("ma_mau") == ma
                     and s.get("survey_kind") == C.KIND_PERSONAL), None)

    def get_survey(self, name):
        return self.surveys.get(name)

    # assignment
    def assignment_by_key(self, key):
        return next((a for a in self.assigns.values() if a["dedupe_key"] == key), None)

    def get_assignment(self, name):
        return self.assigns.get(name)

    def insert_assignment(self, f):
        self._seq += 1
        name = "A%03d" % self._seq
        self.assigns[name] = dict(f, name=name, reminded_at=None)
        return name

    def set_assignment(self, name, values):
        self.assigns[name].update(values)

    def open_assignments(self):
        return [dict(a) for a in self.assigns.values() if a["status"] == C.ASSIGN_OPEN]

    def assignments(self, filters=None):
        rows = list(self.assigns.values())
        for k, v in (filters or {}).items():
            rows = [r for r in rows if r.get(k) == v]
        return [dict(r) for r in rows]

    def assigned_users(self, survey):
        return {a["user"] for a in self.assigns.values() if a["survey"] == survey and a["status"] == "Open"}

    def participants_of_pairs(self, pairs):
        return {p: self.parts[p] for p in pairs if p in self.parts}

    def get_participant(self, survey, user):
        return self.parts.get((survey, user))

    def get_response(self, name):
        return self.responses.get(name)

    # org
    def user_exists(self, user):
        return user in self.emps or user.endswith("@ec.vn")

    def employee_of_user(self, user):
        e = self.emps.get(user)
        return dict(e) if e else None

    def manager_of_user(self, user):
        return (self.emps.get(user) or {}).get("lm")

    def direct_report_users(self, manager):
        return {u for u, e in self.emps.items() if e.get("lm") == manager}

    def user_names(self, users):
        return {u: u.split("@")[0].upper() for u in users}

    def today(self):
        return self._today

    def now(self):
        return dt.datetime.combine(self._today, dt.time(9, 0))

    def ngay_le(self):
        return self.holidays

    def nguoi_di_lam(self, users, day=None):
        return [u for u in users if u not in self.nghi]

    def notify(self, user, title, message, url, survey, dedupe_key, teams=False):
        self.notified.append((user, title, dedupe_key))

    def log_error(self, title):
        self.errors.append(title)

    def site_flag(self, key):
        return False


def _seed(repo, ma="KS_THU_VIEC_1", status=C.STATUS_OPEN, hidden=("q3",), managers="HR\nEC CnB"):
    name = "KS-" + ma
    repo.surveys[name] = {
        "name": name, "ma_mau": ma, "survey_kind": C.KIND_PERSONAL, "status": status,
        "title": "Khảo sát " + ma, "quan_ly_roles": managers, "lm_hidden_items": json.dumps(list(hidden)),
        "mau_tam": 1, "form_json": json.dumps({"v": 1, "items": [
            {"id": "q1", "kind": "question", "type": "scale", "title": "Hướng dẫn đủ?", "scale_min": 1, "scale_max": 5},
            {"id": "q2", "kind": "question", "type": "single", "title": "Khối lượng",
             "options": [{"id": "o1", "label": "Ít"}, {"id": "o2", "label": "Phù hợp"}]},
            {"id": "q3", "kind": "question", "type": "paragraph", "title": "Riêng với HR"}]})}
    return name


class FakeHr:
    def __init__(self, emps, rows):
        self.emps, self.rows = emps, rows

    def nhan_vien_dang_lam(self):
        return [dict(e) for e in self.emps]

    def hop_dong_cua(self, names):
        return {n: list(self.rows.get(n, [])) for n in names}


class TestMoc(unittest.TestCase):
    def test_thu_viec_7_30_45_va_doi_ngay_nghi(self):
        m = moc.cac_moc("Thử việc", D(2026, 11, 2), ngay_nhap=D(2027, 3, 1))
        self.assertEqual([x[1] for x in m], ["KS_THU_VIEC_1", "KS_THU_VIEC_2", "KS_THU_VIEC_3"])
        self.assertEqual(m[0][2], D(2026, 11, 9))       # 2/11 + 7 = T2 9/11
        self.assertEqual(m[1][2], D(2026, 12, 2))       # +30
        self.assertEqual(m[2][2], D(2026, 12, 17))      # +45 = T5
        m2 = moc.cac_moc("Thử việc", D(2026, 11, 7), ngay_nhap=D(2027, 3, 1))   # +7 = CN 14/11 -> T2 16/11
        self.assertEqual(m2[0][2], D(2026, 11, 16))

    def test_thuc_tap_30_60_75(self):
        m = moc.cac_moc("Thực tập", D(2026, 9, 1), ngay_nhap=D(2027, 1, 1))
        # +30 = T5 01/10; +60 = T7 31/10 -> doi sang T2 02/11
        self.assertEqual([x[2] for x in m][:2], [D(2026, 10, 1), D(2026, 11, 2)])
        self.assertEqual(m[2][1], "KS_THUC_TAP_3")

    def test_moc_cuoi_keo_ve_truoc_ngay_tao_nhap(self):
        # thu viec 60 ngay: tu 02/11 -> den 31/12; nhap D-21 = 10/12; D45 = 17/12 >= nhap -> keo ve
        # 2 ngay lam viec truoc 10/12 = 08/12.
        ngay_nhap = D(2026, 12, 10)
        m = moc.cac_moc("Thử việc", D(2026, 11, 2), ngay_nhap=ngay_nhap)
        self.assertEqual(m[-1][2], D(2026, 12, 8))
        self.assertTrue(all(x[2] < ngay_nhap for x in m))

    def test_thu_viec_qua_ngan_bo_moc_giua(self):
        m = moc.cac_moc("Thử việc", D(2026, 11, 2), ngay_nhap=D(2026, 11, 25))
        self.assertTrue(all(x[2] < D(2026, 11, 25) for x in m))
        self.assertNotIn("KS_THU_VIEC_2", [x[1] for x in m])

    def test_chi_giao_moc_dang_mo(self):
        m = moc.cac_moc("Thử việc", D(2026, 11, 2), ngay_nhap=D(2027, 3, 1))
        self.assertIsNone(moc.moc_can_giao(m, D(2026, 11, 8), D(2027, 3, 1)))
        self.assertEqual(moc.moc_can_giao(m, D(2026, 11, 9), D(2027, 3, 1))[1], "KS_THU_VIEC_1")
        # job tat toi tan moc 2 -> chi moc 2, KHONG ban moc 1 tre
        self.assertEqual(moc.moc_can_giao(m, D(2026, 12, 3), D(2027, 3, 1))[1], "KS_THU_VIEC_2")
        self.assertIsNone(moc.moc_can_giao(m, D(2027, 3, 1), D(2027, 3, 1)))


class TestGiao(unittest.TestCase):
    def test_chu_ky_on_dinh_cho_agent_c(self):
        params = list(inspect.signature(ca_nhan.giao_khao_sat).parameters)
        self.assertEqual(params[:5], ["user", "ma_mau", "han_ngay_lv", "ngu_canh", "nguoi_xem_role"])

    def test_giao_han_ngay_lam_viec_va_chong_trung(self):
        r = FakeRepo(today=D(2026, 11, 26))        # T5
        s = _seed(r)
        a = ca_nhan.giao_khao_sat("nv@ec.vn", "KS_THU_VIEC_1", 3, {"khoa": "x"}, "HR,EC CnB,LM", repo=r)
        self.assertTrue(a["ok"])
        self.assertFalse(a["duplicate"])
        self.assertEqual(a["due_date"], "2026-12-01")    # T6, T2, T3
        self.assertEqual(r.assigns[a["assignment"]]["viewer_roles"], "HR\nEC CnB\nLM")
        self.assertEqual(r.assigns[a["assignment"]]["survey"], s)
        self.assertEqual(len(r.notified), 1)
        b = ca_nhan.giao_khao_sat("nv@ec.vn", "KS_THU_VIEC_1", 3, {"khoa": "x"}, "HR", repo=r)
        self.assertTrue(b["duplicate"])
        self.assertEqual(len(r.assigns), 1)
        self.assertEqual(len(r.notified), 1)

    def test_thieu_mau_hoac_mau_dong_khong_nem_loi(self):
        r = FakeRepo()
        self.assertEqual(ca_nhan.giao_khao_sat("nv@ec.vn", "NGHI_VIEC", 2, {}, "HR", repo=r)["ly_do"], "chua_co_mau")
        _seed(r, "NGHI_VIEC", status=C.STATUS_CLOSED)
        self.assertEqual(ca_nhan.giao_khao_sat("nv@ec.vn", "NGHI_VIEC", 2, {}, "HR", repo=r)["ly_do"], "mau_chua_mo")
        self.assertFalse(r.assigns)

    def test_ngu_canh_khong_khoa_van_on_dinh(self):
        k1 = rule.khoa_giao("u", "M", {"b": 1, "a": 2})
        k2 = rule.khoa_giao("u", "M", {"a": 2, "b": 1})
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, rule.khoa_giao("u", "M", {"a": 3}))

    def test_eligible_la_nguoi_duoc_giao(self):
        r = FakeRepo()
        s = _seed(r)
        ca_nhan.giao_khao_sat("nv@ec.vn", "KS_THU_VIEC_1", 3, {"khoa": 1}, None, repo=r)
        self.assertEqual(access.eligible_set(r, r.surveys[s]), {"nv@ec.vn"})


class TestJobMoc(unittest.TestCase):
    def _world(self, today, et="Probation"):
        r = FakeRepo(today=today)
        for i in (1, 2, 3):
            _seed(r, "KS_THU_VIEC_%d" % i)
        hr = FakeHr([{"name": "E1", "user_id": "nv@ec.vn", "employment_type": et, "status": "Active"}],
                    {"E1": [{"name": "R1", "loai_hop_dong": "Thử việc", "tu_ngay": "2026-11-02",
                             "den_ngay": "2026-12-31", "khong_thoi_han": 0}]})
        return r, hr

    def test_giao_dung_moc_va_idempotent(self):
        r, hr = self._world(D(2026, 11, 9))
        self.assertEqual(ca_nhan.giao_khao_sat_moc_job(repo=r, hr=hr), 1)
        self.assertEqual(list(r.assigns.values())[0]["ma_mau"], "KS_THU_VIEC_1")
        self.assertEqual(ca_nhan.giao_khao_sat_moc_job(repo=r, hr=hr), 0)
        self.assertEqual(len(r.assigns), 1)

    def test_khong_chay_ngay_nghi_va_dung_khi_len_chinh_thuc(self):
        r, hr = self._world(D(2026, 11, 14))     # T7
        self.assertEqual(ca_nhan.giao_khao_sat_moc_job(repo=r, hr=hr), 0)
        r, hr = self._world(D(2026, 11, 9), et="Full-time")
        self.assertEqual(ca_nhan.giao_khao_sat_moc_job(repo=r, hr=hr), 0)

    def test_moc_cuoi_truoc_ngay_tao_nhap(self):
        r, hr = self._world(D(2026, 12, 8))      # moc 3 keo ve 08/12 (nhap 10/12)
        ca_nhan.giao_khao_sat_moc_job(repo=r, hr=hr)
        self.assertEqual([a["ma_mau"] for a in r.assigns.values()], ["KS_THU_VIEC_3"])


class TestNhac(unittest.TestCase):
    def _giao(self, today):
        r = FakeRepo(today=today)
        s = _seed(r)
        r.emps["nv@ec.vn"] = {"name": "E1", "status": "Active", "lm": "lm@ec.vn"}
        a = ca_nhan.giao_khao_sat("nv@ec.vn", "KS_THU_VIEC_1", 3, {"khoa": 1}, "HR,LM", repo=r)
        return r, s, a["assignment"]

    def test_nhac_mot_lan_truoc_han_mot_ngay_lv(self):
        r, s, a = self._giao(D(2026, 11, 23))    # T2 -> han T5 26/11, nhac tu T4 25/11
        r._today = D(2026, 11, 24)
        self.assertEqual(ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r), 0)
        r._today = D(2026, 11, 25)
        self.assertEqual(ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r), 1)
        self.assertIsNotNone(r.assigns[a]["reminded_at"])
        r._today = D(2026, 11, 26)
        self.assertEqual(ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r), 0)

    def test_khong_nhac_nguoi_da_nop_hoac_dang_nghi(self):
        r, s, a = self._giao(D(2026, 11, 23))
        r._today = D(2026, 11, 25)
        r.nghi.add("nv@ec.vn")
        self.assertEqual(ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r), 0)
        self.assertIsNone(r.assigns[a]["reminded_at"])
        r.nghi.clear()
        r.parts[(s, "nv@ec.vn")] = {"response": "R1", "submitted_at": "2026-11-24 10:00"}
        self.assertEqual(ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r), 0)

    def test_nv_nghi_viec_huy_lan_giao(self):
        r, s, a = self._giao(D(2026, 11, 23))
        r.emps["nv@ec.vn"]["status"] = "Left"
        r._today = D(2026, 11, 25)
        ca_nhan.nhac_khao_sat_ca_nhan_job(repo=r)
        self.assertEqual(r.assigns[a]["status"], C.ASSIGN_CANCELLED)


class TestQuyenXem(unittest.TestCase):
    def _world(self, viewers="HR,EC CnB,LM", ma="KS_THU_VIEC_1"):
        r = FakeRepo()
        s = _seed(r, ma)
        r.emps["nv@ec.vn"] = {"name": "E1", "status": "Active", "lm": "lm@ec.vn"}
        r.emps["nv2@ec.vn"] = {"name": "E2", "status": "Active", "lm": "lm2@ec.vn"}
        a = ca_nhan.giao_khao_sat("nv@ec.vn", ma, 3, {"khoa": 1}, viewers, repo=r)["assignment"]
        r.parts[(s, "nv@ec.vn")] = {"response": "R1", "submitted_at": "2026-11-24 10:00"}
        r.responses["R1"] = {"answers": {"q1": 4, "q2": {"sel": ["o2"]}, "q3": "Quản lý hay quát"}}
        return r, a

    def ctx(self, user, roles=()):
        return access.Ctx(user, roles)

    def test_hr_xem_du(self):
        r, a = self._world()
        d = ca_nhan.xem_ket_qua(self.ctx("hr@ec.vn", ["HR"]), a, repo=r)
        self.assertEqual(d["quyen"], "full")
        self.assertEqual([x["value"] for x in d["answers"]], ["4", "Phù hợp", "Quản lý hay quát"])

    def test_lm_truc_tiep_bi_an_cau_chi_hr(self):
        r, a = self._world()
        d = ca_nhan.xem_ket_qua(self.ctx("lm@ec.vn", ["Employee"]), a, repo=r)
        self.assertEqual(d["quyen"], "lm")
        self.assertEqual(d["so_cau_an"], 1)
        self.assertNotIn("Quản lý hay quát", json.dumps(d, ensure_ascii=False))

    def test_lm_khac_team_va_nguoi_ngoai_bi_chan(self):
        r, a = self._world()
        for u in ("lm2@ec.vn", "ai@ec.vn"):
            with self.assertRaises(SurveyPermissionError):
                ca_nhan.xem_ket_qua(self.ctx(u, ["Employee"]), a, repo=r)
        self.assertEqual(ca_nhan.danh_sach_ket_qua(self.ctx("lm2@ec.vn", []), repo=r)["rows"], [])
        self.assertEqual(len(ca_nhan.danh_sach_ket_qua(self.ctx("lm@ec.vn", []), repo=r)["rows"]), 1)

    def test_khao_sat_nghi_viec_chi_hr(self):
        r, a = self._world(viewers="HR", ma="NGHI_VIEC")
        with self.assertRaises(SurveyPermissionError):
            ca_nhan.xem_ket_qua(self.ctx("lm@ec.vn", []), a, repo=r)
        with self.assertRaises(SurveyPermissionError):
            ca_nhan.xem_ket_qua(self.ctx("cnb@ec.vn", ["EC CnB"]), a, repo=r)
        self.assertEqual(ca_nhan.xem_ket_qua(self.ctx("hr@ec.vn", ["HR"]), a, repo=r)["quyen"], "full")

    def test_khoi_cho_phieu_danh_gia(self):
        r, a = self._world()
        out = ca_nhan.ket_qua_cho_danh_gia("lm@ec.vn", ["Employee"], "nv@ec.vn", repo=r)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["so_cau_an"], 1)
        self.assertEqual(ca_nhan.ket_qua_cho_danh_gia("ceo@ec.vn", ["EC CEO"], "nv@ec.vn", repo=r), [])

    def test_quan_ly_mau_theo_role(self):
        r, a = self._world()
        s = r.assigns[a]["survey"]
        self.assertTrue(access.can_manage(self.ctx("hr@ec.vn", ["HR"]), r.surveys[s]))
        self.assertFalse(access.can_manage(self.ctx("lm@ec.vn", ["Employee"]), r.surveys[s]))


class TestMauTam(unittest.TestCase):
    def test_seed_7_mau_moi_mau_3_cau_va_an_cau_hr(self):
        from ecentric_workspace.surveys.application import mau_tam
        ts = mau_tam.templates()
        self.assertEqual(sorted(t["ma_mau"] for t in ts),
                         sorted(["KS_THU_VIEC_1", "KS_THU_VIEC_2", "KS_THU_VIEC_3", "KS_THUC_TAP_1",
                                 "KS_THUC_TAP_2", "KS_THUC_TAP_3", "NGHI_VIEC"]))
        for t in ts:
            self.assertEqual(len(t["items"]), 3)
            self.assertTrue(t["hidden"])
        nv = [t for t in ts if t["ma_mau"] == "NGHI_VIEC"][0]
        self.assertEqual(tuple(nv["managers"]), ("HR",))


if __name__ == "__main__":
    unittest.main()
