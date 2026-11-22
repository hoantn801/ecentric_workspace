# Copyright (c) 2026, eCentric and contributors
"""hr/hop_dong/domain.py - nguon ngay cua Danh gia nhan su + khao sat moc (23/11/2026). Thuan.

    python -m pytest ecentric_workspace/hr/tests/test_hop_dong_domain.py
"""
import datetime as dt
import unittest

from ecentric_workspace.hr.hop_dong import domain as hd

D = dt.date


def row(name, loai, tu, den=None, kxd=0):
    return {"name": name, "loai_hop_dong": loai, "tu_ngay": tu, "den_ngay": den, "khong_thoi_han": kxd}


class TestDongHienHanh(unittest.TestCase):
    def test_chon_dong_bat_dau_moi_nhat_da_bat_dau(self):
        rows = [row("a", "Thử việc", "2026-01-01", "2026-02-28"),
                row("b", "HĐLĐ lần 1", "2026-03-01", "2027-02-28"),
                row("c", "HĐLĐ lần 2", "2027-03-01", "2029-02-28")]
        self.assertEqual(hd.dong_hien_hanh(rows, D(2026, 6, 1))["name"], "b")
        self.assertEqual(hd.dong_hien_hanh(rows, D(2026, 1, 15))["name"], "a")
        self.assertIsNone(hd.dong_hien_hanh(rows, D(2025, 12, 31)))

    def test_bo_dong_thieu_tu_ngay(self):
        self.assertIsNone(hd.dong_hien_hanh([row("x", "Thử việc", None, "2026-02-01")], D(2026, 1, 1)))

    def test_loai_danh_gia(self):
        self.assertEqual(hd.loai_danh_gia(row("a", "Thử việc", "2026-01-01")), "Thử việc")
        self.assertEqual(hd.loai_danh_gia(row("a", "Thực tập", "2026-01-01")), "Thực tập")
        self.assertEqual(hd.loai_danh_gia(row("a", "HĐLĐ lần 1", "2026-01-01")), "Hợp đồng")
        self.assertIsNone(hd.loai_danh_gia(row("a", "HĐLĐ lần 3", "2026-01-01", kxd=1)))
        self.assertIsNone(hd.loai_danh_gia(row("a", "Hợp đồng dịch vụ", "2026-01-01")))


class TestLichDanhGia(unittest.TestCase):
    def test_thu_viec_nhap_d21_gui_d14(self):
        den = D(2027, 1, 29)   # thu Sau
        self.assertEqual(hd.ngay_tao_nhap("Thử việc", den), D(2027, 1, 8))
        self.assertEqual(hd.ngay_tu_gui("Thử việc", den), D(2027, 1, 15))

    def test_hop_dong_nhap_d37_gui_d30(self):
        den = D(2027, 3, 31)
        self.assertEqual(hd.ngay_tao_nhap("Hợp đồng", den), den - dt.timedelta(days=37))
        self.assertEqual(hd.ngay_tu_gui("Hợp đồng", den), D(2027, 3, 1))

    def test_moc_roi_cuoi_tuan_lui_ve_thu_sau(self):
        den = D(2027, 1, 31)   # D-14 = CN 17/01 -> T6 15/01
        self.assertEqual(hd.ngay_tu_gui("Thử việc", den), D(2027, 1, 15))
        # ngay le cung lui
        self.assertEqual(hd.ngay_tu_gui("Thử việc", den, {D(2027, 1, 15)}), D(2027, 1, 14))

    def test_thieu_den_ngay(self):
        self.assertIsNone(hd.ngay_tao_nhap("Thử việc", None))


class TestDieu20(unittest.TestCase):
    def test_dem_hd_xac_dinh_thoi_han_va_hd_tiep(self):
        rows = [row("a", "Thử việc", "2024-02-01", "2024-03-31"),
                row("b", "HĐLĐ lần 1", "2024-04-01", "2025-03-31"),
                row("c", "HĐLĐ lần 2", "2025-04-01", "2027-03-31")]
        self.assertEqual(hd.so_hd_xac_dinh_thoi_han(rows), 2)
        self.assertEqual(hd.hdld_tiep_theo(rows), "HĐLĐ lần 3")
        self.assertEqual(hd.ket_thuc_sau_thang(D(2027, 4, 1), 12), D(2028, 3, 31))


class TestThieuNgay(unittest.TestCase):
    def test_probation_khong_dong_goi_y_vao_cong_2_thang(self):
        r = hd.thieu_ngay_ket_thuc({"employment_type": "Probation", "date_of_joining": "2026-11-02"}, [],
                                   D(2026, 11, 23))
        self.assertEqual(r["ly_do"], "Chưa có dòng hợp đồng hiện hành")
        self.assertEqual(r["goi_y_den_ngay"], D(2027, 1, 1))

    def test_dong_thieu_den_ngay(self):
        r = hd.thieu_ngay_ket_thuc({"employment_type": "Intern"},
                                   [row("a", "Thực tập", "2026-10-01")], D(2026, 11, 23))
        self.assertIn("thiếu ngày kết thúc", r["ly_do"])

    def test_khong_thoi_han_va_loai_khac_khong_bao(self):
        self.assertIsNone(hd.thieu_ngay_ket_thuc({"employment_type": "Full-time"},
                                                 [row("a", "HĐLĐ lần 3", "2020-01-01", kxd=1)], D(2026, 1, 1)))
        self.assertIsNone(hd.thieu_ngay_ket_thuc({"employment_type": "Freelancer"}, [], D(2026, 1, 1)))

    def test_het_han_chua_co_dong_moi(self):
        r = hd.thieu_ngay_ket_thuc({"employment_type": "Full-time"},
                                   [row("a", "HĐLĐ lần 1", "2025-01-01", "2025-12-31")], D(2026, 1, 5))
        self.assertIn("hết hạn", r["ly_do"])


if __name__ == "__main__":
    unittest.main()
