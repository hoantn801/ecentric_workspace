# Copyright (c) 2026, eCentric and contributors
"""Nguoi XU LY thay duoc phieu minh phai xu ly tren trang bao cao.

BOI CANH (09/09/2026, chi Dan hoi). Chi Dan la Ke toan, co role EC Finance, va quy
trinh De nghi thanh toan khai Fulfiller = Role EC Finance. Bo may duyet coi chi la
nguoi xu ly hop le: trang form mo tab xu ly cho chi. Nhung trang "Tat ca yeu cau" lai
hoi mot cau HOAN TOAN KHAC (`reporting/scope.py`) - chi co bon tang admin / truong
phong / nguoi duyet / nguoi gui - nen chi khong thay MOT phieu nao.

Trang do VAN kiem "duoc xu ly khong", nhung chi de HIEN NUT tren nhung dong da lot qua
bo loc. Dong khong hien thi nut khong bao gio xuat hien. Do la ly do phai sua o TANG
LOC, khong phai o tang nut.

Va cai dang so hon: chi Lien thay duoc het KHONG phai vi duoc cap quyen xem, ma vi chi
la nguoi duyet cap 2 cua MOI phieu -> co dong approver tren tung phieu -> roi vao tang
`approver`. Quyen xem dang phu thuoc vao mot chuyen khong lien quan.

Bo test nay giu bon dieu:
  1. Co `fulfil_types` -> dieu kien loc PHAI co ve theo loai phieu, va dung THAM SO.
  2. Ve do KHONG duoc lam mat cac ve cu (phieu cua minh / phieu minh duyet / phong minh).
  3. Khong co `fulfil_types` -> dieu kien y het truoc day (khong ai bong dung thay them).
  4. Admin khong doi gi; `can_export` khong doi (nguoi xu ly KHONG duoc xuat toan bo).
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _load(rel_parts, fake_frappe):
    """Nap mot module voi frappe gia. exec(compile(...)) chu khong import: __pycache__
    tung lam moi dot bien song sot (bai hoc 31/08)."""
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fake_frappe
    try:
        mod = types.ModuleType("under_test_" + rel_parts[-1])
        exec(compile(_read(*rel_parts), rel_parts[-1], "exec"), mod.__dict__)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


def _fake_frappe(**kw):
    fk = types.ModuleType("frappe")
    fk.session = types.SimpleNamespace(user=kw.get("session_user", "x@ec.vn"))
    fk.get_roles = lambda u=None: kw.get("roles", [])
    fk.get_all = kw.get("get_all", lambda *a, **k: [])

    class _DB(object):
        def exists(self, dt, filters=None):
            return kw.get("exists", False)
    fk.db = _DB()

    class _Meta(object):
        def has_field(self, f):
            return f in kw.get("dept_fields", ())
    fk.get_meta = lambda dt: _Meta()
    return fk


_SCOPE = ("approval_center", "reporting", "scope.py")


class TestDieuKienLoc(unittest.TestCase):
    """scope_predicate la ham thuan - nap rieng, chay that."""

    def _sp(self):
        return _load(_SCOPE, _fake_frappe()).scope_predicate

    def test_nguoi_gui_co_loai_xu_ly_thi_thay_ca_loai_do(self):
        sql, params = self._sp()({"mode": "requester", "user": "dan@ec.vn",
                                  "fulfil_types": ["PAYMENT_REQUEST"]})
        self.assertIn("r.requested_by = %(scope_user)s", sql, "van phai thay phieu cua minh")
        self.assertIn("r.approval_type = %(scope_ft_0)s", sql)
        self.assertEqual(params["scope_ft_0"], "PAYMENT_REQUEST")

    def test_ma_loai_di_bang_THAM_SO_chu_khong_noi_chuoi(self):
        """Noi thang ma loai vao SQL la mot lo tiem chich - va ma loai co the den tu
        du lieu cau hinh, khong phai hang so trong code."""
        sql, params = self._sp()({"mode": "requester", "user": "u", "fulfil_types": ["A'; DROP--"]})
        self.assertNotIn("DROP", sql)
        self.assertEqual(params["scope_ft_0"], "A'; DROP--")

    def test_nhieu_loai_thi_moi_loai_mot_tham_so(self):
        sql, params = self._sp()({"mode": "requester", "user": "u",
                                  "fulfil_types": ["A", "B", "C"]})
        for i, t in enumerate("ABC"):
            self.assertIn("%%(scope_ft_%d)s" % i, sql)
            self.assertEqual(params["scope_ft_%d" % i], t)

    def test_KHONG_lam_mat_ve_cu(self):
        sp = self._sp()
        sql, _ = sp({"mode": "approver", "user": "u", "fulfil_types": ["A"]})
        self.assertIn("tabEC Approval Request Approver", sql, "van phai thay phieu minh duyet")
        self.assertIn("r.requested_by", sql)
        sql2, p2 = sp({"mode": "department", "user": "u", "departments": ["D1"],
                       "fulfil_types": ["A"]})
        self.assertIn("r.requester_department IN", sql2, "van phai thay phieu phong minh")
        self.assertEqual(p2["scope_dept_0"], "D1")
        self.assertIn("r.approval_type", sql2)

    def test_khong_co_loai_xu_ly_thi_Y_HET_truoc_day(self):
        """Khong ai bong dung thay them - day la ve an toan cua ban sua nay."""
        sp = self._sp()
        self.assertEqual(sp({"mode": "requester", "user": "u"})[0],
                         "r.requested_by = %(scope_user)s")
        self.assertEqual(sp({"mode": "requester", "user": "u", "fulfil_types": []})[0],
                         "r.requested_by = %(scope_user)s")
        appr = sp({"mode": "approver", "user": "u", "fulfil_types": []})[0]
        self.assertTrue(appr.startswith("(") and "OR" in appr)
        self.assertNotIn("approval_type", appr)

    def test_admin_khong_doi(self):
        self.assertEqual(self._sp()({"mode": "admin", "user": "u", "fulfil_types": ["A"]}),
                         ("1=1", {}))

    def test_mode_la(self):
        """Tang khong ro thi van chi thay phieu minh (+ loai minh xu ly), khong mo rong."""
        sql, _ = self._sp()({"mode": "khong-biet", "user": "u", "fulfil_types": ["A"]})
        self.assertNotIn("requester_department", sql)
        self.assertNotIn("Approver", sql)


class TestResolveScope(unittest.TestCase):
    def test_admin_khong_can_hoi_loai_xu_ly(self):
        mod = _load(_SCOPE, _fake_frappe(roles=["System Manager"]))
        sc = mod.resolve_scope("a@ec.vn")
        self.assertEqual(sc["mode"], "admin")
        self.assertEqual(sc["fulfil_types"], [])

    def test_moi_tang_deu_mang_theo_fulfil_types(self):
        for roles, exists, dept_fields, expect in (
                ([], False, (), "requester"),
                ([], True, (), "approver")):
            mod = _load(_SCOPE, _fake_frappe(roles=roles, exists=exists,
                                             dept_fields=dept_fields))
            mod._fulfil_types = lambda u: ["PAYMENT_REQUEST"]
            sc = mod.resolve_scope("dan@ec.vn")
            self.assertEqual(sc["mode"], expect)
            self.assertEqual(sc["fulfil_types"], ["PAYMENT_REQUEST"])

    def test_hoi_loai_xu_ly_HONG_thi_fail_closed(self):
        """Hoi bo may duyet ma HONG (import loi / DB loi) thi KHONG duoc lam vo trang,
        va cung khong duoc mo rong nham -> tra []. Day la ve an toan: mat mot ve OR
        thi nguoi dung thay it hon, chap nhan duoc; nem loi thi ca trang trang xoa."""
        mod = _load(_SCOPE, _fake_frappe())
        self.assertEqual(mod._fulfil_types("u"), [],
                         "khong nap duoc permissions.py -> phai tra rong, khong nem loi")
        # va resolve_scope van chay binh thuong khi cho do hong
        sc = mod.resolve_scope("u@ec.vn")
        self.assertEqual(sc["fulfil_types"], [])
        self.assertEqual(sc["mode"], "requester")


class TestKhongDuocDE_HAI_HE_LECH_NHAU(unittest.TestCase):
    """Cai bay goc: hai cho cung tra loi 'ai xu ly loai nao' bang hai doan code khac
    nhau thi mot ngay nao do chung lech, va khong ai biet."""

    def test_scope_hoi_bo_may_duyet_chu_khong_tu_tra(self):
        src = _read("approval_center", "reporting", "scope.py")
        self.assertIn("permissions as _perm", src)
        self.assertIn("_perm.fulfilled_approval_types", src)
        self.assertNotIn("participant_purpose", src,
                         "scope.py dang TU tra bang Fulfiller - phai hoi permissions.py")

    def test_ham_nguon_su_that_nam_canh_is_fulfiller_participant(self):
        src = _read("approval_center", "shared", "workflow", "permissions.py")
        tree = ast.parse(src)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertIn("fulfilled_approval_types", names)
        self.assertIn("is_fulfiller_participant", names)

    def test_hai_ham_dung_CUNG_bo_loc(self):
        """Neu mai ai do doi participant_purpose o mot ham ma quen ham kia."""
        src = _read("approval_center", "shared", "workflow", "permissions.py")
        tree = ast.parse(src)
        fns = {n.name: ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ("is_fulfiller_participant", "fulfilled_approval_types"):
            body = fns[name]
            self.assertIn("'Fulfiller'", body.replace('"', "'"), name)
            self.assertIn("'EC Approval Process'", body.replace('"', "'"), name)
            self.assertIn("source_type", body, name)
            self.assertIn("frappe.get_roles", body, "%s phai xet ca dong Role" % name)


class TestFulfilledApprovalTypes(unittest.TestCase):
    """Chay ham THAT tren mot frappe gia - khong grep source."""

    def _mod(self, participants, procs, roles):
        def get_all(dt, filters=None, fields=None, **k):
            if dt == "EC Approval Process":
                return list(procs)
            if dt == "EC Approval Participant":
                out = []
                for p in participants:
                    if p.get("source_type") != (filters or {}).get("source_type"):
                        continue
                    if (filters or {}).get("user") and p.get("user") != filters["user"]:
                        continue
                    out.append(p)
                return out
            return []
        return _load(("approval_center", "shared", "workflow", "permissions.py"),
                     _fake_frappe(get_all=get_all, roles=roles))

    _PROCS = [{"name": "PR-V1", "approval_type": "PAYMENT_REQUEST"},
              {"name": "LV-V1", "approval_type": "LEAVE_REQUEST"}]

    def test_theo_ROLE(self):
        mod = self._mod([{"parent": "PR-V1", "source_type": "Role", "role": "EC Finance"}],
                        self._PROCS, ["EC Finance", "Employee"])
        self.assertEqual(mod.fulfilled_approval_types("dan@ec.vn"), ["PAYMENT_REQUEST"])

    def test_theo_USER(self):
        mod = self._mod([{"parent": "LV-V1", "source_type": "User", "user": "hr@ec.vn"}],
                        self._PROCS, [])
        self.assertEqual(mod.fulfilled_approval_types("hr@ec.vn"), ["LEAVE_REQUEST"])

    def test_khong_co_role_do_thi_KHONG_duoc_tinh(self):
        mod = self._mod([{"parent": "PR-V1", "source_type": "Role", "role": "EC Finance"}],
                        self._PROCS, ["Employee"])
        self.assertEqual(mod.fulfilled_approval_types("ai@ec.vn"), [])

    def test_Guest_va_rong(self):
        """Dat cau hinh sao cho NEU bo chot Guest thi Guest se duoc tinh la nguoi xu ly:
        mot dong Fulfiller theo Role, va Guest mang dung role do. Chot con thi -> []."""
        mod = self._mod([{"parent": "PR-V1", "source_type": "Role", "role": "EC Finance"}],
                        self._PROCS, ["EC Finance"])
        self.assertEqual(mod.fulfilled_approval_types("Guest"), [],
                         "Guest khong bao gio la nguoi xu ly")
        self.assertEqual(mod.fulfilled_approval_types(None), [])
        self.assertEqual(mod.fulfilled_approval_types(""), [])
        # ...va voi mot nguoi that thi cung cau hinh do PHAI ra ket qua (neu khong,
        # phep kiem tren xanh chi vi du lieu gia khong khop cai gi ca).
        self.assertEqual(mod.fulfilled_approval_types("dan@ec.vn"), ["PAYMENT_REQUEST"])

    def test_khong_co_quy_trinh_Active_thi_rong(self):
        mod = self._mod([{"parent": "PR-V1", "source_type": "Role", "role": "EC Finance"}],
                        [], ["EC Finance"])
        self.assertEqual(mod.fulfilled_approval_types("dan@ec.vn"), [])

    def test_chi_lay_quy_trinh_dang_Active(self):
        seen = {}

        def get_all(dt, filters=None, fields=None, **k):
            if dt == "EC Approval Process":
                seen["f"] = dict(filters or {})
                return list(self._PROCS)
            return []
        mod = _load(("approval_center", "shared", "workflow", "permissions.py"),
                    _fake_frappe(get_all=get_all, roles=[]))
        mod.fulfilled_approval_types("u@ec.vn")
        self.assertEqual(seen["f"].get("status"), "Active",
                         "quy trinh Draft/Retired khong duoc cho quyen xem")


class TestXuatDuLieuKhongDoi(unittest.TestCase):
    def test_nguoi_xu_ly_KHONG_duoc_xuat_toan_bo(self):
        mod = _load(_SCOPE, _fake_frappe())
        self.assertFalse(mod.can_export({"mode": "requester", "fulfil_types": ["A"]}))
        self.assertTrue(mod.can_export({"mode": "admin"}))


if __name__ == "__main__":
    unittest.main()
