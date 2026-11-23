# Copyright (c) 2026, eCentric and contributors
"""Danh gia nhan su (EMPLOYEE_REVIEW, 23/11/2026 - HR Dot 2).

Code THAT cua features/employee_review/{domain,application} chay tren frappe gia + engine gia +
repository gia (service nhan repo / hr qua tham so). Kiem:
  1. Dieu 25: "Gia han" thu viec chi khi chua gia han va con duoi tran; ngay moi khong vuot tran;
     tran doc theo chuc danh / chuc vu, mac dinh 60. Thuc tap gia han khong rang buoc.
  2. Dieu 20: da co 2 HD xac dinh thoi han -> chi con "Khong xac dinh thoi han".
  3. LM bat buoc ket qua + nhan xet; thoi han HD bat buoc khi Dat (thu viec) / Gia han (HD).
  4. Nhap som D-21 / D-37, tu gui dung D-14 / D-30 (khong truoc), khong chay ngay nghi, khong trung.
  5. Thieu LM / thieu ngay / NV chua co tai khoan -> KHONG tao phieu, bao C&B.
  6. An nhan xet LM voi NV toi khi CEO duyet (ke ca NV giu role HR); nguoi khac trong luong thay.
  7. Gui: engine.submit(activate_first_level=False) -> khoi phuc cap NV/LM bi bo -> kich hoat cap 1.
  8. Duyet chay o cap 1/2 bi chan (phai nop noi dung); comment cap NV/LM la cau chung; khong co Tu choi.
  9. Sau CEO: chi DE XUAT cap nhat ho so; C&B xac nhan moi ghi.
 10. Dang ky: registry, _FULFILLMENT_HANDLERS, hooks scheduler, patches.txt, seed type.
"""
import datetime as dt
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_APP = os.path.abspath(os.path.join(_AC, ".."))
D = dt.date


class _Throw(Exception):
    pass


class _Perm(_Throw):
    pass


CALLS = []
SESSION = types.SimpleNamespace(user="cnb@ec.vn")


def _install():
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = SESSION
    fr.flags = types.SimpleNamespace(get=lambda k, d=None: None)
    fr.PermissionError = _Perm
    fr.ValidationError = _Throw
    fr.conf = {}

    def throw(msg, exc=None):
        raise (exc or _Throw)(msg)
    fr.throw = throw
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.parse_json = lambda s: json.loads(s) if isinstance(s, str) else s
    fr.get_traceback = lambda: "tb"
    fr.log_error = lambda *a, **k: CALLS.append(("log_error", a, k))
    fr.get_roles = lambda u=None: ["Employee"]
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda v=None: v
    utils.now_datetime = lambda: dt.datetime(2026, 11, 23, 9, 0)
    utils.nowdate = lambda: "2026-11-23"
    fr.utils = utils
    fr.db = types.SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils

    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")

    def rec(name):
        def f(*a, **k):
            CALLS.append((name, a, k))
            return "REQ-1" if name == "submit" else None
        return f
    for n in ("submit", "approve", "request_information", "resubmit", "cancel", "notify",
              "log_action", "_activate_level"):
        setattr(eng, n, rec(n))
    eng.request_label = lambda dt_, name, t=None: name
    sys.modules[eng.__name__] = eng
    nc = types.ModuleType("ecentric_workspace.notification_center.nhip_gui")
    nc.gop_tin_job = lambda f: f
    sys.modules[nc.__name__] = nc
    ev = types.ModuleType("ecentric_workspace.notification_center.events")
    ev.publish_notification_event = lambda *a, **k: CALLS.append(("publish", a, k))
    sys.modules[ev.__name__] = ev
    import ecentric_workspace.notification_center as ncpkg
    ncpkg.events = ev
    ncpkg.nhip_gui = nc


_install()

from ecentric_workspace.approval_center.features.employee_review.domain import luat  # noqa: E402
from ecentric_workspace.approval_center.features.employee_review.application import service, jobs  # noqa: E402


def _calls(name):
    return [c for c in CALLS if c[0] == name]


class Doc(types.SimpleNamespace):
    def get(self, k, d=None):
        return getattr(self, k, d)

    def update(self, d):
        for k, v in d.items():
            setattr(self, k, v)

    def get_doc_before_save(self):
        return None

    def is_new(self):
        return False


ROW_TV = {"name": "R1", "loai_hop_dong": "Thử việc", "tu_ngay": "2026-11-02", "den_ngay": "2026-12-31",
          "khong_thoi_han": 0}


class FakeHr:
    def __init__(self):
        self.emps = {"E1": {"name": "E1", "employee_name": "Nguyễn Thị D", "user_id": "nv@ec.vn",
                            "status": "Active", "employment_type": "Probation", "designation": "Chuyên viên",
                            "grade": "Nhân viên", "department": "Ops", "company": "EC"}}
        self.rows = {"E1": [dict(ROW_TV)]}
        self.lm = {"E1": "lm@ec.vn"}
        self.active_users = {"nv@ec.vn", "lm@ec.vn"}
        self.writes = []

    def nhan_vien(self, n):
        return dict(self.emps[n]) if n in self.emps else None

    def nhan_vien_dang_lam(self):
        return [dict(e) for e in self.emps.values() if e["status"] == "Active"]

    def hop_dong_cua(self, names):
        return {n: [dict(r) for r in self.rows.get(n, [])] for n in names}

    def user_dang_hoat_dong(self, u):
        return u in self.active_users

    def quan_ly_truc_tiep(self, n):
        return self.lm.get(n)

    def cap_dong_hop_dong(self, employee, values=None, sua_dong=None, employment_type=None):
        self.writes.append((employee, values, sua_dong, employment_type))


class FakeRepo:
    OPEN = ("Pending", "Information Required")

    def __init__(self, today=D(2026, 12, 10)):
        self._today = today
        self.docs = {}
        self.cfg = {"tat_tu_dong": 0, "nguoi_gui_mac_dinh": None, "tran_mac_dinh": 60, "quy_tac": []}
        self.req = {}            # req -> {approval_status, current_level, pending: {level: [users]}}
        self.roles = {"cnb@ec.vn": ["EC CnB"], "hr@ec.vn": ["HR"], "ceo@ec.vn": ["EC CEO"]}
        self.restored = []
        self.activated = []
        self.skipped_lv = {}
        self.da_gh = False

    def today(self):
        return self._today

    def now(self):
        return dt.datetime.combine(self._today, dt.time(9))

    def ngay_le(self):
        return set()

    def settings(self):
        return dict(self.cfg)

    def roles_of(self, u):
        return self.roles.get(u, ["Employee"])

    def users_with_roles(self, roles):
        return sorted(u for u, rs in self.roles.items() if set(rs) & set(roles))

    def nguoi_gui_mac_dinh(self, cfg, tranh=()):
        u = cfg.get("nguoi_gui_mac_dinh")
        if u and u not in tranh:
            return u
        return next((x for x in ("cnb@ec.vn", "cnb2@ec.vn") if x not in tranh), None)

    def mau_tieu_chi(self, loai):
        return "Mẫu tạm", [{"tieu_chi": "Kết quả"}, {"tieu_chi": "Thái độ"}]

    def tieu_chi_cua_mau(self, n):
        return []

    def review_by_key(self, key):
        return next((n for n, d in self.docs.items() if d.dedupe_key == key), None)

    def insert_review(self, fields):
        name = "EV-%d" % (len(self.docs) + 1)
        base = {k: None for k in ("approval_request", "lm_ket_qua", "lm_thoi_han_hd", "lm_gia_han_den",
                                  "ket_qua", "ho_so_trang_thai", "ho_so_de_xuat_json", "nv_nhan_xet",
                                  "lm_nhan_xet", "lm_danh_gia_json", "nv_danh_gia_json")}
        base.update(da_huy_nhap=0)
        base.update(fields)
        self.docs[name] = Doc(name=name, **base)
        return name

    def get_review(self, name, for_update=False):
        return self.docs[name]

    def save(self, doc):
        pass

    def set_review(self, name, values):
        self.docs[name].update(values)

    def drafts_due(self, hom_nay):
        return [n for n, d in self.docs.items() if d.auto_draft and not d.da_huy_nhap
                and not d.approval_request and d.auto_submit_on and d.auto_submit_on <= hom_nay]

    def reviews(self, filters=None, fields=None):
        out = []
        for d in self.docs.values():
            if all(getattr(d, k, None) == v for k, v in (filters or {}).items()):
                out.append(dict(vars(d)))
        return out

    def request_info(self, r):
        return dict(self.req[r], name=r) if r in self.req else None

    def request_statuses(self, names):
        return {n: dict(self.req[n], name=n) for n in names if n in self.req}

    def level_names(self, names):
        return {}

    def cap_dang_cho_toi(self, r, user):
        info = self.req.get(r)
        if not info or info["approval_status"] != "Pending":
            return None
        lv = info["current_level"]
        return lv if user in info["pending"].get(lv, []) else None

    def la_nguoi_duyet_tu_cap(self, r, user, lv):
        info = self.req.get(r) or {}
        return any(user in us for l, us in (info.get("pending") or {}).items() if l >= lv)

    def level_status(self, r, lv):
        return self.skipped_lv.get((r, lv))

    def khoi_phuc_cap_bi_bo(self, r, levels, ly_do):
        self.restored.append((r, tuple(levels)))
        return []

    def kich_hoat_cap_dau(self, r):
        self.activated.append(r)

    def dat_cap_tra_lai(self, r, lv):
        self.req[r]["back_to"] = lv

    def da_gia_han_thu_viec(self, n):
        return self.da_gh

    def json_load(self, s, default):
        try:
            v = json.loads(s) if s else default
            return v if isinstance(v, type(default)) else default
        except (TypeError, ValueError):
            return default


def _req(repo, doc, level, status="Pending"):
    doc.approval_request = "REQ-1"
    repo.req["REQ-1"] = {"approval_status": status, "current_level": level,
                         "pending": {1: ["nv@ec.vn"], 2: ["lm@ec.vn"], 3: ["ceo@ec.vn"]}}


# =========================================================================== luat thuan --
class TestDieu25(unittest.TestCase):
    def test_gia_han_trong_tran_va_ngay_toi_da(self):
        dong = {"tu_ngay": "2026-11-02", "den_ngay": "2026-12-01"}      # 30 ngay < 60
        c = luat.lua_chon("Thử việc", dong, [], 60, False)
        gh = [o for o in c["ket_qua"] if o["value"] == "Gia hạn"][0]
        self.assertTrue(gh["enabled"])
        self.assertEqual(c["gia_han_toi_da"], "2026-12-31")              # tu + 59 ngay

    def test_cham_tran_60_khong_gia_han(self):
        dong = {"tu_ngay": "2026-11-02", "den_ngay": "2026-12-31"}      # 60 ngay
        c = luat.lua_chon("Thử việc", dong, [], 60, False)
        gh = [o for o in c["ket_qua"] if o["value"] == "Gia hạn"][0]
        self.assertFalse(gh["enabled"])
        self.assertIn("trần 60", gh["ly_do"])
        self.assertIsNone(c["gia_han_toi_da"])

    def test_da_gia_han_mot_lan_khong_cho_lan_hai(self):
        c = luat.lua_chon("Thử việc", {"tu_ngay": "2026-11-02", "den_ngay": "2026-11-30"}, [], 180, True)
        self.assertFalse([o for o in c["ket_qua"] if o["value"] == "Gia hạn"][0]["enabled"])

    def test_tran_theo_chuc_danh_roi_chuc_vu(self):
        q = [{"ap_dung": "Chức vụ", "gia_tri": "BOD", "tran_ngay": 180},
             {"ap_dung": "Chức danh", "gia_tri": "Kỹ thuật viên", "tran_ngay": 30}]
        self.assertEqual(luat.tran_thu_viec({"designation": "Kỹ thuật viên", "grade": "BOD"}, q, 60), 30)
        self.assertEqual(luat.tran_thu_viec({"designation": "GĐ", "grade": "BOD"}, q, 60), 180)
        self.assertEqual(luat.tran_thu_viec({"designation": "X"}, q, None), 60)

    def test_lm_chon_ngay_vuot_tran_bi_chan(self):
        dong = {"tu_ngay": "2026-11-02", "den_ngay": "2026-12-01"}
        c = luat.lua_chon("Thử việc", dong, [], 60, False)
        p = {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "Cần thêm thời gian", "lm_gia_han_den": "2027-01-05"}
        with self.assertRaises(luat.LoiDanhGia):
            luat.kiem_danh_gia_lm("Thử việc", p, c, "2026-12-01")
        p["lm_gia_han_den"] = "2026-12-31"
        self.assertEqual(luat.kiem_danh_gia_lm("Thử việc", p, c, "2026-12-01")["lm_gia_han_den"], "2026-12-31")

    def test_lm_chon_gia_han_khi_bi_khoa_bi_chan_o_server(self):
        c = luat.lua_chon("Thử việc", {"tu_ngay": "2026-11-02", "den_ngay": "2026-12-31"}, [], 60, False)
        with self.assertRaises(luat.LoiDanhGia):
            luat.kiem_danh_gia_lm("Thử việc", {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "x" * 20,
                                               "lm_gia_han_den": "2027-01-10"}, c, "2026-12-31")

    def test_thuc_tap_gia_han_khong_rang_buoc(self):
        c = luat.lua_chon("Thực tập", {"tu_ngay": "2026-01-01", "den_ngay": "2026-12-31"}, [], 60, True)
        self.assertTrue(all(o["enabled"] for o in c["ket_qua"]))
        self.assertIsNone(c["gia_han_toi_da"])


class TestDieu20(unittest.TestCase):
    ROWS = [{"loai_hop_dong": "HĐLĐ lần 1", "khong_thoi_han": 0},
            {"loai_hop_dong": "HĐLĐ lần 2", "khong_thoi_han": 0}]

    def test_sau_hai_hd_chi_con_khong_thoi_han(self):
        c = luat.lua_chon("Hợp đồng", {"tu_ngay": "2025-04-01", "den_ngay": "2027-03-31"}, self.ROWS)
        en = [o["value"] for o in c["thoi_han"] if o["enabled"]]
        self.assertEqual(en, ["Không xác định thời hạn"])
        with self.assertRaises(luat.LoiDanhGia):
            luat.kiem_danh_gia_lm("Hợp đồng", {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "Tốt, gia hạn tiếp",
                                               "lm_thoi_han_hd": "24 tháng"}, c, "2027-03-31")

    def test_mot_hd_con_chon_duoc_xac_dinh(self):
        c = luat.lua_chon("Hợp đồng", {"tu_ngay": "2026-01-01", "den_ngay": "2026-12-31"}, self.ROWS[:1])
        self.assertTrue(all(o["enabled"] for o in c["thoi_han"]))

    def test_nhan_xet_va_thoi_han_bat_buoc(self):
        c = luat.lua_chon("Hợp đồng", {"tu_ngay": "2026-01-01", "den_ngay": "2026-12-31"}, [])
        with self.assertRaises(luat.LoiDanhGia):
            luat.kiem_danh_gia_lm("Hợp đồng", {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "ok"}, c, "2026-12-31")
        with self.assertRaises(luat.LoiDanhGia):
            luat.kiem_danh_gia_lm("Hợp đồng", {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "Hoàn thành tốt"}, c, "2026-12-31")
        ok = luat.kiem_danh_gia_lm("Hợp đồng", {"lm_ket_qua": "Không gia hạn", "lm_nhan_xet": "Không đạt KPI cả năm"},
                                   c, "2026-12-31")
        self.assertIsNone(ok["lm_thoi_han_hd"])


class TestDeXuatHoSo(unittest.TestCase):
    def test_thu_viec_dat_them_hdld_va_full_time(self):
        d = luat.de_xuat_ho_so("Thử việc", "Đạt", ROW_TV, [ROW_TV], "12 tháng")
        self.assertEqual(d["kieu"], "them_dong")
        self.assertEqual(d["dong_moi"]["loai_hop_dong"], "HĐLĐ lần 1")
        self.assertEqual((d["dong_moi"]["tu_ngay"], d["dong_moi"]["den_ngay"]), ("2027-01-01", "2027-12-31"))
        self.assertEqual(d["employment_type"], "Full-time")

    def test_gia_han_thu_viec_sua_den_ngay_dong_hien_hanh(self):
        d = luat.de_xuat_ho_so("Thử việc", "Gia hạn", ROW_TV, [ROW_TV], None, "2027-01-15")
        self.assertEqual(d["kieu"], "sua_den_ngay")
        self.assertEqual(d["sua"], {"dong": "R1", "den_ngay": "2027-01-15"})

    def test_khong_dat_khong_doi_ho_so(self):
        self.assertEqual(luat.de_xuat_ho_so("Thử việc", "Không đạt", ROW_TV, [ROW_TV])["kieu"], "khong")

    def test_hop_dong_kxd(self):
        r = {"name": "R2", "loai_hop_dong": "HĐLĐ lần 2", "tu_ngay": "2025-04-01", "den_ngay": "2027-03-31"}
        d = luat.de_xuat_ho_so("Hợp đồng", "Gia hạn", r, [{"loai_hop_dong": "HĐLĐ lần 1"}, r], "Không xác định thời hạn")
        self.assertEqual(d["dong_moi"]["loai_hop_dong"], "HĐLĐ lần 3")
        self.assertEqual(d["dong_moi"]["khong_thoi_han"], 1)
        self.assertIsNone(d["dong_moi"]["den_ngay"])


class TestAnNhanXetLM(unittest.TestCase):
    def test_nv_khong_thay_toi_khi_ceo_duyet_ke_ca_giu_role_hr(self):
        self.assertFalse(luat.xem_phan_lm("nv@ec.vn", "nv@ec.vn", False, ["HR", "EC CnB"], True, True))
        self.assertTrue(luat.xem_phan_lm("nv@ec.vn", "nv@ec.vn", True, []))

    def test_lm_ceo_cnb_thay_nguoi_ngoai_khong(self):
        self.assertTrue(luat.xem_phan_lm("lm@ec.vn", "nv@ec.vn", False, [], approver_tu_cap_2=True))
        self.assertTrue(luat.xem_phan_lm("hr@ec.vn", "nv@ec.vn", False, ["HR"]))
        self.assertFalse(luat.xem_phan_lm("ai@ec.vn", "nv@ec.vn", False, ["Employee"]))


# =========================================================================== service --
class _Base(unittest.TestCase):
    def setUp(self):
        del CALLS[:]
        SESSION.user = "cnb@ec.vn"
        self.repo, self.hr = FakeRepo(), FakeHr()
        service.default_repo = self.repo
        self._orig_hr = service._hr
        service._hr = lambda: self.hr

    def tearDown(self):
        service._hr = self._orig_hr

    def draft(self, **kw):
        res = service.tao_nhap("E1", auto=True, hom_nay=kw.pop("hom_nay", D(2026, 12, 10)), repo=self.repo, hr=self.hr)
        return self.repo.docs[res["name"]]


class TestTaoNhap(_Base):
    def test_nhap_som_d21_va_ngay_tu_gui_d14(self):
        # den 31/12/2026 (T5): nhap D-21 = T5 10/12; tu gui D-14 = T5 17/12
        res = service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        self.assertTrue(res["ok"])
        doc = self.repo.docs[res["name"]]
        self.assertEqual(doc.auto_submit_on, D(2026, 12, 17))
        self.assertEqual(doc.requested_by, "cnb@ec.vn")
        self.assertEqual(doc.employee_user, "nv@ec.vn")
        self.assertEqual(doc.line_manager, "lm@ec.vn")
        self.assertEqual(len(json.loads(doc.tieu_chi_json)), 2)
        self.assertIsNone(doc.approval_request)
        self.assertFalse(_calls("submit"))

    def test_nguoi_gui_khong_trung_nv_hoac_lm(self):
        """Tich hop Dot 0 (23/11): engine loai nguoi gui khoi cap duyet -> nguoi gui trung NV / LM la mat buoc."""
        self.repo.cfg["nguoi_gui_mac_dinh"] = "lm@ec.vn"
        res = service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        self.assertTrue(res["ok"])
        self.assertNotIn(self.repo.docs[res["name"]].requested_by, ("lm@ec.vn", "nv@ec.vn"))
        res2 = service.tao_nhap("E1", auto=False, actor="lm@ec.vn", hom_nay=D(2026, 12, 12),
                                repo=self.repo, hr=self.hr)
        self.assertTrue(res2.get("duplicate") or res2.get("ly_do") == "nguoi_gui_trung")

    def test_chua_toi_d21_job_khong_tao(self):
        res = service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 9), repo=self.repo, hr=self.hr)
        self.assertEqual(res["ly_do"], "chua_toi_han")

    def test_khong_tao_trung(self):
        a = service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        b = service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 11), repo=self.repo, hr=self.hr)
        self.assertTrue(b["duplicate"])
        self.assertEqual(a["name"], b["name"])
        self.assertEqual(len(self.repo.docs), 1)

    def test_thieu_lm_thieu_ngay_thieu_tai_khoan_khong_tao(self):
        self.hr.lm = {}
        self.assertEqual(service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)["ly_do"], "thieu_lm")
        self.hr.lm = {"E1": "lm@ec.vn"}
        self.hr.active_users = {"lm@ec.vn"}
        self.assertEqual(service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)["ly_do"], "thieu_tai_khoan")
        self.hr.active_users = {"nv@ec.vn", "lm@ec.vn"}
        self.hr.rows["E1"][0]["den_ngay"] = None
        self.assertEqual(service.tao_nhap("E1", auto=True, hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)["ly_do"], "thieu_ngay")
        self.assertFalse(self.repo.docs)

    def test_hop_dong_nhap_d37(self):
        self.hr.rows["E1"] = [{"name": "R9", "loai_hop_dong": "HĐLĐ lần 1", "tu_ngay": "2026-04-01",
                               "den_ngay": "2027-03-31", "khong_thoi_han": 0}]
        self.assertEqual(service.tao_nhap("E1", auto=True, hom_nay=D(2027, 2, 21), repo=self.repo, hr=self.hr)["ly_do"], "chua_toi_han")
        res = service.tao_nhap("E1", auto=True, hom_nay=D(2027, 2, 22), repo=self.repo, hr=self.hr)
        self.assertTrue(res["ok"])
        self.assertEqual(self.repo.docs[res["name"]].auto_submit_on, D(2027, 3, 1))


class TestJob(_Base):
    def test_job_tao_nhap_roi_tu_gui_dung_ngay(self):
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        self.assertEqual((out["tao"], out["gui"]), (1, 0))
        doc = list(self.repo.docs.values())[0]
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 16), repo=self.repo, hr=self.hr)
        self.assertEqual((out["tao"], out["gui"]), (0, 0))
        self.assertIsNone(doc.approval_request)
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 17), repo=self.repo, hr=self.hr)
        self.assertEqual(out["gui"], 1)
        self.assertEqual(doc.approval_request, "REQ-1")
        sub = _calls("submit")[0]
        self.assertEqual(sub[1][3], "cnb@ec.vn")                                   # nguoi gui = C&B
        self.assertEqual(sub[2]["process_code"], "EMPLOYEE_REVIEW_TV-V1")
        self.assertIs(sub[2]["activate_first_level"], False)
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 18), repo=self.repo, hr=self.hr)
        self.assertEqual(len(_calls("submit")), 1)                                # khong gui lai

    def test_nhap_vua_tao_khi_ngay_gui_da_qua_thi_doi_lan_chay_sau(self):
        """Lan chay dau sau deploy: hop dong het 31/12, ngay tu gui (17/12) da qua. Khong tao roi gui
        ngay trong cung lan chay - C&B co mot ngay lam viec de xem; lan chay ke moi gui."""
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 28), repo=self.repo, hr=self.hr)
        self.assertEqual((out["tao"], out["gui"]), (1, 0))
        self.assertFalse(_calls("submit"))
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 29), repo=self.repo, hr=self.hr)
        self.assertEqual(out["gui"], 1)
        self.assertEqual(len(_calls("submit")), 1)

    def test_job_khong_chay_ngay_nghi(self):
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 12), repo=self.repo, hr=self.hr)   # T7
        self.assertEqual(out, {"tao": 0, "gui": 0, "thieu": 0, "huy": 0})

    def test_job_thieu_lm_bao_cnb_khong_tao(self):
        self.hr.lm = {}
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        self.assertEqual(out["thieu"], 1)
        self.assertFalse(self.repo.docs)
        keys = [c[2]["dedupe_key"] for c in _calls("publish")]
        self.assertTrue(keys and all("thieu|E1|Thử việc|2026-12-31" in k for k in keys))

    def test_job_tat_bang_settings(self):
        self.repo.cfg["tat_tu_dong"] = 1
        self.assertEqual(jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)["tao"], 0)

    def test_tu_gui_khi_lm_vua_mat_thi_khong_gui_va_bao(self):
        jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 10), repo=self.repo, hr=self.hr)
        self.hr.lm = {}
        out = jobs.tao_nhap_va_tu_gui_job(hom_nay=D(2026, 12, 17), repo=self.repo, hr=self.hr)
        self.assertEqual(out["gui"], 0)
        self.assertFalse(_calls("submit"))

    def test_nhac_thu_hai_thieu_ngay(self):
        self.hr.rows["E1"][0]["den_ngay"] = None
        self.assertEqual(jobs.nhac_thieu_ngay_job(hom_nay=D(2026, 12, 14), repo=self.repo, hr=self.hr), 1)
        self.assertTrue(_calls("publish"))


class TestGuiVaLuong(_Base):
    def test_gui_khoi_phuc_cap_truoc_khi_kich_hoat(self):
        doc = self.draft()
        service.submit(doc.name, repo=self.repo, hr=self.hr)
        self.assertEqual(self.repo.restored, [("REQ-1", (1, 2))])
        self.assertEqual(self.repo.activated, ["REQ-1"])
        self.assertEqual(doc.approval_request, "REQ-1")
        self.assertEqual(doc.auto_draft, 0)

    def test_chi_cnb_gui_duoc(self):
        doc = self.draft()
        SESSION.user = "ai@ec.vn"
        with self.assertRaises(_Perm):
            service.submit(doc.name, repo=self.repo, hr=self.hr)

    def test_duyet_chay_cap_1_2_bi_chan_cap_3_can_phan_lm(self):
        doc = self.draft()
        _req(self.repo, doc, 1)
        SESSION.user = "nv@ec.vn"
        with self.assertRaises(_Throw):
            service.approve(doc.name, repo=self.repo)
        self.repo.req["REQ-1"]["current_level"] = 2
        SESSION.user = "lm@ec.vn"
        with self.assertRaises(_Throw):
            service.approve(doc.name, repo=self.repo)
        self.repo.req["REQ-1"]["current_level"] = 3
        SESSION.user = "ceo@ec.vn"
        with self.assertRaises(_Throw):
            service.approve(doc.name, repo=self.repo)
        doc.lm_ket_qua = "Đạt"
        service.approve(doc.name, repo=self.repo)
        self.assertEqual(len(_calls("approve")), 1)

    def test_nv_tu_danh_gia_comment_chung(self):
        doc = self.draft()
        _req(self.repo, doc, 1)
        SESSION.user = "nv@ec.vn"
        with self.assertRaises(_Throw):
            service.nop_tu_danh_gia(doc.name, {"nv_diem": {"0": {"diem": 4}}}, repo=self.repo)   # thieu tieu chi 2
        service.nop_tu_danh_gia(doc.name, {"nv_diem": {"0": {"diem": 4}, "1": {"diem": 5}}}, repo=self.repo)
        ap = _calls("approve")[-1]
        self.assertEqual(ap[2]["comment"], service.COMMENT_NV)
        SESSION.user = "lm@ec.vn"           # nguoi khac khong tu danh gia ho
        with self.assertRaises(_Perm):
            service.nop_tu_danh_gia(doc.name, {"nv_diem": {}}, repo=self.repo)

    def test_lm_nop_bat_buoc_nhan_xet_va_comment_khong_lo_noi_dung(self):
        doc = self.draft()
        _req(self.repo, doc, 2)
        SESSION.user = "lm@ec.vn"
        with self.assertRaises(_Throw):
            service.nop_danh_gia_lm(doc.name, {"lm_ket_qua": "Đạt", "lm_nhan_xet": ""}, repo=self.repo, hr=self.hr)
        secret = "Hoàn thành tốt KPI, cần cải thiện báo cáo tuần"
        service.nop_danh_gia_lm(doc.name, {"lm_ket_qua": "Đạt", "lm_nhan_xet": secret, "lm_thoi_han_hd": "12 tháng"},
                                repo=self.repo, hr=self.hr)
        ap = _calls("approve")[-1]
        self.assertNotIn("KPI", ap[2]["comment"])
        self.assertEqual(doc.lm_ket_qua, "Đạt")
        self.assertEqual(doc.lm_boi, "lm@ec.vn")

    def test_lm_chon_gia_han_cham_tran_bi_chan(self):
        doc = self.draft()
        _req(self.repo, doc, 2)
        SESSION.user = "lm@ec.vn"
        with self.assertRaises(_Throw):
            service.nop_danh_gia_lm(doc.name, {"lm_ket_qua": "Gia hạn", "lm_nhan_xet": "Cần thêm thời gian",
                                               "lm_gia_han_den": "2027-01-15"}, repo=self.repo, hr=self.hr)

    def test_lm_la_ceo_nhap_phan_lm_o_cap_ceo(self):
        doc = self.draft()
        doc.line_manager = "ceo@ec.vn"
        _req(self.repo, doc, 3)
        self.repo.skipped_lv[("REQ-1", 2)] = "Skipped"
        SESSION.user = "ceo@ec.vn"
        res = service.nop_danh_gia_lm(doc.name, {"lm_ket_qua": "Không đạt", "lm_nhan_xet": "Không đạt yêu cầu vị trí"},
                                      repo=self.repo, hr=self.hr)
        self.assertFalse(res["da_gui"])
        self.assertFalse(_calls("approve"))
        service.approve(doc.name, repo=self.repo)
        self.assertEqual(len(_calls("approve")), 1)

    def test_tra_lai_va_khong_co_tu_choi(self):
        doc = self.draft()
        _req(self.repo, doc, 3)
        SESSION.user = "ceo@ec.vn"
        service.tra_lai(doc.name, "Xem lại nhận xét", repo=self.repo)
        self.assertEqual(self.repo.req["REQ-1"]["back_to"], 2)
        self.assertEqual(len(_calls("request_information")), 1)
        self.assertEqual(len(_calls("resubmit")), 1)
        with self.assertRaises(_Throw):
            service.reject(doc.name, "x")


class TestRedactVaSauCeo(_Base):
    def _detail_biz(self, doc):
        return dict(vars(doc))

    def test_redact_nv_truoc_va_sau_ceo(self):
        doc = self.draft()
        _req(self.repo, doc, 3)
        doc.lm_ket_qua, doc.lm_nhan_xet = "Đạt", "Bí mật của LM"
        req = types.SimpleNamespace(get=lambda k, d=None: {"approval_status": "Pending", "name": "REQ-1"}.get(k, d))
        SESSION.user = "nv@ec.vn"
        self.repo.roles["nv@ec.vn"] = ["HR"]
        biz = self._detail_biz(doc)
        orig = service.default_repo
        service.redact(biz, req)
        self.assertNotIn("lm_nhan_xet", biz)
        self.assertNotIn("lm_ket_qua", biz)
        SESSION.user = "lm@ec.vn"
        biz = self._detail_biz(doc)
        service.redact(biz, req)
        self.assertEqual(biz["lm_nhan_xet"], "Bí mật của LM")
        SESSION.user = "nv@ec.vn"
        req2 = types.SimpleNamespace(get=lambda k, d=None: {"approval_status": "Approved", "name": "REQ-1"}.get(k, d))
        biz = self._detail_biz(doc)
        service.redact(biz, req2)
        self.assertEqual(biz["lm_nhan_xet"], "Bí mật của LM")
        self.assertIs(service.default_repo, orig)

    def test_sau_ceo_chi_de_xuat_cnb_xac_nhan_moi_ghi(self):
        doc = self.draft()
        _req(self.repo, doc, 3, status="Approved")
        doc.lm_ket_qua, doc.lm_thoi_han_hd = "Đạt", "12 tháng"
        service.on_final_approval(doc.name, repo=self.repo, hr=self.hr)
        self.assertEqual(doc.ho_so_trang_thai, "Chờ C&B xác nhận")
        self.assertFalse(self.hr.writes)
        service.on_final_approval(doc.name, repo=self.repo, hr=self.hr)          # idempotent
        SESSION.user = "ai@ec.vn"
        with self.assertRaises(_Perm):
            service.xac_nhan_ho_so(doc.name, {}, repo=self.repo, hr=self.hr)
        SESSION.user = "cnb@ec.vn"
        service.xac_nhan_ho_so(doc.name, {"so_hop_dong": "HD-01"}, repo=self.repo, hr=self.hr)
        emp, values, sua, et = self.hr.writes[0]
        self.assertEqual(values["loai_hop_dong"], "HĐLĐ lần 1")
        self.assertEqual(values["so_hop_dong"], "HD-01")
        self.assertEqual(et, "Full-time")
        self.assertEqual(doc.ho_so_trang_thai, "Đã cập nhật hồ sơ")
        with self.assertRaises(_Throw):
            service.xac_nhan_ho_so(doc.name, {}, repo=self.repo, hr=self.hr)    # khong ghi lan hai

    def test_khong_dat_khong_can_cap_nhat(self):
        doc = self.draft()
        _req(self.repo, doc, 3, status="Approved")
        doc.lm_ket_qua = "Không đạt"
        service.on_final_approval(doc.name, repo=self.repo, hr=self.hr)
        self.assertEqual(doc.ho_so_trang_thai, "Không cần cập nhật")


# =========================================================================== dang ky --
def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class TestDangKy(unittest.TestCase):
    def test_registry_handler_hooks_patches_seed(self):
        self.assertIn("EMPLOYEE_REVIEW_DEFINITION", _read("approval_center", "shared", "registry.py"))
        self.assertIn('"EC Employee Review": "ecentric_workspace.approval_center.features.employee_review.'
                      'application.service.on_final_approval"',
                      _read("approval_center", "shared", "workflow", "transitions.py"))
        hooks = _read("hooks.py")
        for m in ("employee_review.application.jobs.tao_nhap_va_tu_gui_job",
                  "surveys.application.ca_nhan.giao_khao_sat_moc_job",
                  "surveys.application.ca_nhan.nhac_khao_sat_ca_nhan_job",
                  "employee_review.application.jobs.nhac_thieu_ngay_job"):
            self.assertEqual(hooks.count(m), 1, m)
        self.assertIn('"0 9 * * 1"', hooks)
        pt = _read("patches.txt")
        self.assertIn("approval_center.patches.p450_danh_gia_nhan_su", pt)
        self.assertIn("surveys.patches.p002_mau_khao_sat_ca_nhan", pt)
        seed = json.loads(_read("approval_center", "seed", "approval_types_seed.json"))
        self.assertIn("EMPLOYEE_REVIEW", [r["approval_code"] for r in seed])

    def test_truong_lm_o_permlevel_1(self):
        d = json.loads(_read("approval_center", "doctype", "ec_employee_review", "ec_employee_review.json"))
        lv = {f["fieldname"]: f.get("permlevel", 0) for f in d["fields"]}
        for f in luat.LM_FIELDS:
            self.assertEqual(lv.get(f), 1, f)
        self.assertEqual(lv["nv_danh_gia_json"], 0)

    def test_definition_redactor_va_quick(self):
        src = _read("approval_center", "features", "employee_review", "domain", "definition.py")
        self.assertIn('business_redactor=ServiceMethod(_BASE, "redact")', src)
        self.assertIn("quick_comment_required=True", src)
        self.assertNotIn("lm_", src.split("quick_summary")[1])



# --------------------------------------------------- tieu de tuy chinh (Hoan chot 23/11) --
class _DocTruoc(Doc):
    """Doc co ban luu truoc (get_doc_before_save) - mo phong save_draft tren phieu da co."""
    def get_doc_before_save(self):
        return self.__dict__.get("_truoc")


class TestTieuDeTuyChinh(_Base):
    def _doc(self, truoc=None, **kw):
        base = dict(name="EV-9", review_type="Thử việc", ten_nhan_vien="Nguyễn Thị D", nhan_vien="E1",
                    hd_den_ngay="2026-12-31", approval_request=None, da_huy_nhap=0, mau_tieu_chi=None,
                    custom_title=None)
        d = _DocTruoc(**dict(base, **kw))
        d._truoc = Doc(**dict(base, **truoc)) if truoc is not None else None
        return d

    def test_gen_title_dung_custom_neu_co(self):
        auto = service.tieu_de_tu_sinh({"review_type": "Thử việc", "ten_nhan_vien": "Nguyễn Thị D",
                                         "hd_den_ngay": "2026-12-31"})
        self.assertEqual(auto, "Đánh giá thử việc - Nguyễn Thị D - đến 31/12/2026")
        self.assertEqual(service.gen_title({"review_type": "Thử việc", "ten_nhan_vien": "Nguyễn Thị D",
                                            "hd_den_ngay": "2026-12-31", "custom_title": "   "}), auto)
        self.assertEqual(service.gen_title({"review_type": "Thử việc", "custom_title": "  Đánh giá  cuối thử việc  "}),
                         "Đánh giá cuối thử việc")
        self.assertEqual(len(service.gen_title({"custom_title": "x" * 300})), service.CUSTOM_TITLE_MAX)

    def test_tao_nhap_van_dung_tieu_de_tu_sinh(self):
        doc = self.draft()
        self.assertEqual(doc.request_title, "Đánh giá thử việc - Nguyễn Thị D - đến 31/12/2026")

    def test_cnb_sua_o_nhap_duoc_va_chuan_hoa(self):
        SESSION.user = "cnb@ec.vn"
        d = self._doc(truoc={}, custom_title="  Đánh giá   đặc biệt ")
        service.prepare_draft(d)
        self.assertEqual(d.custom_title, "Đánh giá đặc biệt")
        d2 = self._doc(truoc={"custom_title": "Cũ"}, custom_title="")
        service.prepare_draft(d2)                                   # xoa tieu de = quay ve tu sinh
        self.assertIsNone(d2.custom_title)

    def test_chan_sau_khi_gui(self):
        SESSION.user = "cnb@ec.vn"
        d = self._doc(truoc={"approval_request": "REQ-1"}, approval_request="REQ-1", custom_title="Mới")
        with self.assertRaises(_Throw):
            service.prepare_draft(d)
        # Phieu "Can bo sung" gui lai nguyen tieu de cu -> khong chan.
        d = self._doc(truoc={"approval_request": "REQ-1", "custom_title": "Cũ"}, approval_request="REQ-1",
                      custom_title="Cũ")
        service.prepare_draft(d)
        d = self._doc(truoc={"approval_request": "REQ-1", "custom_title": "Cũ"}, approval_request="REQ-1",
                      custom_title=None)
        with self.assertRaises(_Throw):
            service.prepare_draft(d)

    def test_chi_cnb_va_nhap_chua_huy(self):
        SESSION.user = "nv@ec.vn"
        with self.assertRaises(_Perm):
            service.prepare_draft(self._doc(truoc={}, custom_title="Lạ"))
        SESSION.user = "cnb@ec.vn"
        with self.assertRaises(_Throw):
            service.prepare_draft(self._doc(truoc={"da_huy_nhap": 1}, da_huy_nhap=1, custom_title="Lạ"))

    def test_review_block_o_tieu_de_dung_vai_tro(self):
        doc = self.draft()
        biz = dict(vars(doc))
        SESSION.user = "cnb@ec.vn"
        x = service.review_block(biz, None, self.repo, self.hr)["danh_gia"]
        self.assertEqual(x["sua_tieu_de"], 1)
        self.assertEqual(x["tieu_de_tu_sinh"], "Đánh giá thử việc - Nguyễn Thị D - đến 31/12/2026")
        SESSION.user = "nv@ec.vn"
        self.assertEqual(service.review_block(biz, None, self.repo, self.hr)["danh_gia"]["sua_tieu_de"], 0)
        SESSION.user = "cnb@ec.vn"
        biz["approval_request"] = "REQ-1"
        self.assertEqual(service.review_block(biz, None, self.repo, self.hr)["danh_gia"]["sua_tieu_de"], 0)

    def test_definition_va_doctype(self):
        from ecentric_workspace.approval_center.features.employee_review.domain.definition import (
            EMPLOYEE_REVIEW_DEFINITION as DEF)
        self.assertIn("custom_title", DEF.editable_fields)
        d = json.loads(_read("approval_center", "doctype", "ec_employee_review", "ec_employee_review.json"))
        f = next(x for x in d["fields"] if x["fieldname"] == "custom_title")
        self.assertEqual((f["fieldtype"], f["label"], f.get("permlevel", 0)), ("Data", "Tiêu đề (tuỳ chỉnh)", 0))
        self.assertFalse(f.get("reqd"))

    def test_controller_khoa_sau_khi_gui(self):
        """Lop DocType chan doi custom_title sau khi gui tren MOI duong ghi (ke ca rong -> co)."""
        if "frappe.model.document" not in sys.modules:
            m1, m2 = types.ModuleType("frappe.model"), types.ModuleType("frappe.model.document")
            m2.Document = type("Document", (object,), {})
            sys.modules["frappe.model"], sys.modules["frappe.model.document"] = m1, m2
        from ecentric_workspace.approval_center.doctype.ec_employee_review.ec_employee_review import ECEmployeeReview
        lock = ECEmployeeReview._title_lock
        d = self._doc(truoc={"approval_request": "REQ-1"}, approval_request="REQ-1", custom_title="Mới")
        d.is_new = lambda: False
        with self.assertRaises(_Throw):
            lock(d)
        d = self._doc(truoc={}, approval_request=None, custom_title="Mới")
        d.is_new = lambda: False
        lock(d)                                                   # nhap: duoc sua
        d = self._doc(truoc={"approval_request": "REQ-1", "custom_title": "A"}, approval_request="REQ-1",
                      custom_title="A")
        d.is_new = lambda: False
        lock(d)


if __name__ == "__main__":
    unittest.main()
