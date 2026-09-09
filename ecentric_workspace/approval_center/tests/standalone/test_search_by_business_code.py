# Copyright (c) 2026, eCentric and contributors
"""O tim kiem cua "Tat ca yeu cau" phai tra duoc bang MA PHIEU.

Do that 09/09/2026. Hoan cam ma phieu EC-PAYR-2026-00053 (lay tu mot thong bao ky so)
va tra tren trang "Tat ca yeu cau" - khong ra gi, ket luan "khong tim thay phieu".
That ra phieu do dang nam ngay tren man hinh, duoi ma HO SO DUYET EC-APR-2026-00166.

HAI cho cung gay ra mot cam giac:
  * Bang chi HIEN ma ho so duyet, khong hien ma phieu -> Ctrl+F cua trinh duyet chiu.
  * O tim kiem cua trang truoc day cung chi tra `r.name` (ma ho so duyet), tieu de,
    nguoi gui, phong ban - KHONG tra `r.reference_name` (ma phieu).
Nen ca hai duong deu tac. Bo test nay giu duong thu hai.

Ve tim kiem la mot dieu kien LOC, khong phai quyen: no van duoc AND voi scope_predicate
o `_list_where`, nen mo rong no khong lam ai thay them phieu cua nguoi khac. Test cuoi
giu dung dieu do - vi neu mai ai do "toi uu" bang cach OR no vao ngoai pham vi thi day
la mot lo ro du lieu, khong phai mot cai o tim kiem rong rai.
"""
import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn(name):
    """Nap RIENG mot ham thuan tu queries.py (ca module can frappe)."""
    src = _read("approval_center", "reporting", "queries.py")
    node = next(n for n in ast.parse(src).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "queries.py", "exec"), ns)
    return ns[name]


class TestTimTheoMaPhieu(unittest.TestCase):
    def setUp(self):
        self.clause = _fn("_search_clause")

    def test_co_tra_theo_ma_phieu(self):
        params = {}
        sql = self.clause("EC-PAYR-2026-00053", params)
        self.assertIn("r.reference_name LIKE %(search)s", sql,
                      "go ma phieu vao o tim kiem phai ra - do la ma nguoi dung cam tren tay")
        self.assertEqual(params["search"], "%EC-PAYR-2026-00053%")

    def test_van_tra_theo_ma_ho_so_duyet_va_cac_ve_cu(self):
        """Them ve moi khong duoc lam mat ve cu."""
        sql = self.clause("x", {})
        for ve in ("r.name LIKE", "t.approval_title LIKE",
                   "r.requested_by LIKE", "r.requester_department LIKE"):
            self.assertIn(ve, sql, ve)

    def test_di_bang_THAM_SO_va_co_bao_ca_hai_dau(self):
        params = {}
        self.clause("  EC-PAYR-1  ", params)
        self.assertEqual(params["search"], "%EC-PAYR-1%", "phai cat khoang trang thua")
        sql = self.clause("' OR 1=1 --", {})
        self.assertNotIn("1=1", sql, "chuoi nguoi dung KHONG duoc noi vao SQL")

    def test_khong_go_gi_thi_khong_them_dieu_kien(self):
        for empty in (None, "", 0):
            self.assertIsNone(self.clause(empty, {}))

    def test_moi_ve_deu_nam_TRONG_mot_cap_ngoac(self):
        """Thieu ngoac thi khi AND voi pham vi xem, mot ve OR se thoat ra ngoai va
        nguoi dung thay phieu cua nguoi khac. Day la loi kinh dien cua SQL noi chuoi."""
        sql = self.clause("x", {})
        self.assertTrue(sql.startswith("(") and sql.endswith(")"), sql)


class TestVeTimKiemKHONGPhaiQuyen(unittest.TestCase):
    def test_dieu_kien_tim_kiem_duoc_AND_voi_pham_vi_xem(self):
        src = _read("approval_center", "reporting", "queries.py")
        node = next(n for n in ast.parse(src).body
                    if isinstance(n, ast.FunctionDef) and n.name == "_list_where")
        body = ast.unparse(node)
        self.assertIn("scope_predicate", body, "pham vi xem phai luon co mat")
        self.assertIn("_search_clause", body)
        # ca hai deu di vao cung mot danh sach `where` roi noi bang AND
        self.assertNotIn(" OR ", body.replace("OR r.", ""),
                         "dieu kien tim kiem khong duoc OR ra ngoai pham vi xem")

    def test_where_noi_bang_AND(self):
        src = _read("approval_center", "reporting", "queries.py")
        self.assertIn('" AND ".join(where)', src)


if __name__ == "__main__":
    unittest.main()
