# Copyright (c) 2026, eCentric and contributors
"""Ba dau hieu ngoai le cua tab "Tao hang loat". Chay code THAT voi frappe gia.

HAI PHEP KIEM DAT NHAT:

  `test_khong_bao_gio_nem` - dau hieu la thu tang them. Neu mot loi SQL o day nem ra thi
  ca man hinh tao phieu chet, va cai gia do lon hon nhieu lan ich loi cua ba cai co.

  `test_lich_su_so_tien_chi_tra_phieu_CUA_CHINH_MINH` - day la rang buoc RIENG TU, khong
  phai rang buoc chuc nang, nen no khong bao gio tu lo ra khi man hinh chay dung. Go
  `owner` khoi cau SQL thi moi thu van xanh, chi la ai cung doc duoc lich su chi tieu cua
  nguoi khac. Mot rang buoc kieu do phai co test rieng hoac no se bi go trong mot lan
  refactor nao do ma khong ai nhan ra.

Moi luat co mot mau DAT va mot mau TRUOT (A56).
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(
    _HERE, "..", "..", "features", "payment_request", "application", "batch_flags.py"))

TOI = "hoan.tran@ecentric.vn"


def _load(sql=None):
    """sql: callable(query, params) -> list[tuple] ; hoac nem de mo phong su co."""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=TOI)
    goi = []

    def _sql(query, params=None, **kw):
        goi.append((query, params))
        if sql is None:
            return []
        return sql(query, params)
    fk.db = types.SimpleNamespace(sql=_sql)
    fk.get_all = lambda *a, **k: []

    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fk
    try:
        m = types.ModuleType("_batch_flags_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "batch_flags.py", "exec"), m.__dict__)
        m._goi = goi
        return m
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


def _dong(key, acc, amount=1000000):
    return {"key": key, "bank_account_number": acc, "payment_amount": amount}


class TestTrungTrongLo(unittest.TestCase):
    def test_hai_dong_cung_so_tai_khoan_deu_bi_danh_dau(self):
        m = _load()
        ra = m.flag_rows([_dong("a", "9857672398"), _dong("b", "9857672398"),
                          _dong("c", "1111222233")])
        self.assertTrue(ra["a"]["dup_in_batch"])
        self.assertTrue(ra["b"]["dup_in_batch"])
        self.assertFalse(ra["c"]["dup_in_batch"])

    def test_dau_cach_va_dau_cham_KHONG_lam_thanh_hai_so_khac_nhau(self):
        # "0123 456 789" va "0123.456.789" la MOT so tai khoan. So sanh nguyen chuoi thi
        # dung cai truong hop nguy hiem nhat - mot khoan sap bi tra hai lan - lot luoi.
        m = _load()
        ra = m.flag_rows([_dong("a", "0123 456 789"), _dong("b", "0123.456.789")])
        self.assertTrue(ra["a"]["dup_in_batch"])
        self.assertTrue(ra["b"]["dup_in_batch"])

    def test_mot_dong_thi_khong_trung_voi_ai(self):
        m = _load()
        self.assertFalse(m.flag_rows([_dong("a", "9857672398")])["a"]["dup_in_batch"])


class TestSoTaiKhoanMoi(unittest.TestCase):
    def test_chua_tung_co_phieu_da_gui_thi_la_MOI(self):
        m = _load(sql=lambda q, p: [])
        self.assertTrue(m.flag_rows([_dong("a", "9857672398")])["a"]["new_account"])

    def test_da_tung_co_phieu_da_gui_thi_KHONG_moi(self):
        m = _load(sql=lambda q, p: [("EC-PAYR-2026-00042",)])
        self.assertFalse(m.flag_rows([_dong("a", "9857672398")])["a"]["new_account"])

    def test_chi_tinh_phieu_DA_GUI_chu_khong_tinh_ban_nhap(self):
        m = _load(sql=lambda q, p: [])
        m.flag_rows([_dong("a", "9857672398")])
        q = m._goi[0][0]
        self.assertIn("submitted_at", q)
        self.assertIn("!= ''", q)

    def test_so_sanh_tren_chuoi_DA_CHUAN_HOA_ca_hai_dau(self):
        # Chuan hoa mot ben thoi thi "0123 456 789" trong DB khong bao gio khop voi
        # "0123456789" vua go - ca hai dau hieu truot am tham, khong ai thay gi.
        m = _load(sql=lambda q, p: [])
        m.flag_rows([_dong("a", "0123 456 789")])
        q, params = m._goi[0]
        self.assertIn("REPLACE", q)
        self.assertEqual(params[0], "0123456789")

    def test_KHONG_gioi_han_theo_owner(self):
        # Co y: dau hieu chi manh khi no tra toan cong ty. Neu chi tra phieu cua chinh
        # minh thi moi nguoi nhan quen thuoc cua dong nghiep deu bao "moi" - nhieu den
        # muc nguoi ta tat mat.
        m = _load(sql=lambda q, p: [])
        m.flag_rows([{"key": "a", "bank_account_number": "9857672398"}])
        self.assertNotIn("owner", m._goi[0][0])


class TestSoTienLechXa(unittest.TestCase):
    def _sql_lich_su(self, amounts):
        def _s(q, p):
            if "payment_amount" in q:
                return [(a,) for a in amounts]
            return [("da-tung-co",)]
        return _s

    def test_gap_hon_ba_lan_trung_vi_thi_bao(self):
        m = _load(sql=self._sql_lich_su([1000000, 1000000, 1200000]))
        ra = m.flag_rows([_dong("a", "9857672398", 5000000)])
        self.assertTrue(ra["a"]["amount_off"])

    def test_nho_hon_mot_phan_ba_trung_vi_thi_bao(self):
        m = _load(sql=self._sql_lich_su([3000000, 3000000, 3000000]))
        self.assertTrue(m.flag_rows([_dong("a", "9857672398", 200000)])["a"]["amount_off"])

    def test_gap_doi_thi_KHONG_bao(self):
        # 2 lan la chuyen thuong ngay voi KOL/KOC. Bao o day la bao suot ngay, va mot
        # canh bao keu suot ngay thi khong con la canh bao.
        m = _load(sql=self._sql_lich_su([1000000, 1000000, 1000000]))
        self.assertFalse(m.flag_rows([_dong("a", "9857672398", 2000000)])["a"]["amount_off"])

    def test_it_lich_su_qua_thi_IM_LANG(self):
        m = _load(sql=self._sql_lich_su([1000000, 1000000]))
        self.assertFalse(m.flag_rows([_dong("a", "9857672398", 90000000)])["a"]["amount_off"])

    def test_khong_co_lich_su_nao_thi_IM_LANG(self):
        m = _load(sql=self._sql_lich_su([]))
        self.assertFalse(m.flag_rows([_dong("a", "9857672398", 90000000)])["a"]["amount_off"])

    def test_lich_su_so_tien_chi_tra_phieu_CUA_CHINH_MINH(self):
        m = _load(sql=self._sql_lich_su([1000000, 1000000, 1000000]))
        m.flag_rows([_dong("a", "9857672398", 5000000)])
        cau = [g for g in m._goi if "payment_amount" in g[0]]
        self.assertTrue(cau, "phai co cau truy van lich su so tien")
        q, params = cau[0]
        self.assertIn("owner", q)
        self.assertIn(TOI, list(params))


class TestKhongNo(unittest.TestCase):
    def test_khong_bao_gio_nem(self):
        def _no(q, p):
            raise RuntimeError("bang khoa")
        m = _load(sql=_no)
        ra = m.flag_rows([_dong("a", "9857672398", 5000000)])
        self.assertEqual(ra["a"], {"new_account": False, "dup_in_batch": False,
                                   "amount_off": False})

    def test_dong_khong_co_key_bi_bo_qua(self):
        m = _load()
        self.assertEqual(m.flag_rows([{"bank_account_number": "1"}]), {})

    def test_dong_khong_co_so_tai_khoan_khong_tra_truy_van_nao(self):
        m = _load()
        ra = m.flag_rows([{"key": "a", "bank_account_number": ""}])
        self.assertEqual(ra["a"], {"new_account": False, "dup_in_batch": False,
                                   "amount_off": False})
        self.assertEqual(m._goi, [])

    def test_rong_va_None_deu_khong_no(self):
        m = _load()
        self.assertEqual(m.flag_rows([]), {})
        self.assertEqual(m.flag_rows(None), {})

    def test_so_tien_rac_khong_lam_nga(self):
        m = _load(sql=lambda q, p: [])
        ra = m.flag_rows([{"key": "a", "bank_account_number": "9857672398",
                           "payment_amount": "ba trieu"}])
        self.assertFalse(ra["a"]["amount_off"])


class TestChiTraBoolean(unittest.TestCase):
    def test_khong_he_lo_so_lan_so_tien_hay_ten_ai(self):
        # Gia tri canh bao nam o chu "moi". Moi chi tiet them la mot cai oracle khong ai xin.
        m = _load(sql=lambda q, p: [(5000000,)] * 5)
        ra = m.flag_rows([_dong("a", "9857672398", 1000000)])
        self.assertEqual(set(ra["a"].keys()), {"new_account", "dup_in_batch", "amount_off"})
        for v in ra["a"].values():
            self.assertIsInstance(v, bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
