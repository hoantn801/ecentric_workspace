# Copyright (c) 2026, eCentric and contributors
"""Test luat nhom Phan hoi phe duyet - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_approval_rules -v

Nhom nay cham diem NGUOI DUYET tren mot luong dang chay that va cham vao tien
that. Mot luat sai o day khong lam lech mot con so - no lam mot nguoi duyet
dung han bi ghi la tre, va nguoi do se khong tin bang diem nua, mai mai.
"""
import datetime
import unittest

from ecentric_workspace.sla.domain import approval_rules as ar

DUE = datetime.datetime(2026, 9, 22, 17, 0)
TRUOC = datetime.datetime(2026, 9, 22, 16, 0)
SAU = datetime.datetime(2026, 9, 23, 9, 0)


class TestAttemptNo(unittest.TestCase):
    def test_chua_chay_lai_thi_la_lan_1(self):
        self.assertEqual(ar.attempt_no(0), 1)
        self.assertEqual(ar.attempt_no(None), 1)

    def test_moi_lan_restart_la_mot_lan_moi(self):
        self.assertEqual(ar.attempt_no(1), 2)
        self.assertEqual(ar.attempt_no(3), 4)

    def test_gia_tri_rac_khong_lam_vo(self):
        # `count` doc tu DB; mot ban ghi hong khong duoc lam ca luong duyet chet.
        for v in ("", "x", -5, [], {}):
            self.assertEqual(ar.attempt_no(v), 1, repr(v))


class TestOverrideOutcome(unittest.TestCase):
    def test_ep_duyet_sau_han_van_tinh_tre(self):
        # Chu so huu chot 17/09. Khong co duong thoat: mot nguoi da tre ba ngay
        # khong duoc xoa vet nho mot lenh ep duyet.
        act, reason = ar.override_outcome(DUE, SAU)
        self.assertEqual(act, ar.ACT_MISSED)
        self.assertIsNone(reason)

    def test_ep_duyet_truoc_han_thi_loai_tru(self):
        act, reason = ar.override_outcome(DUE, TRUOC)
        self.assertEqual(act, ar.ACT_EXCLUDE)
        self.assertEqual(reason, ar.REASON_OVERRIDE)

    def test_dung_dung_han_khong_phai_tre(self):
        # `>` chu khong phai `>=`: bam dung giay cuoi cung van la trong han.
        act, _ = ar.override_outcome(DUE, DUE)
        self.assertEqual(act, ar.ACT_EXCLUDE)

    def test_khong_co_han_thi_khong_the_tre(self):
        act, reason = ar.override_outcome(None, SAU)
        self.assertEqual(act, ar.ACT_EXCLUDE)
        self.assertEqual(reason, ar.REASON_OVERRIDE)

    def test_dung_thuoc_do_duoc_truyen_vao(self):
        # Han theo GIO LAM VIEC phai do tre bang gio lam viec. Truyen ham so
        # sanh vao de nhanh do khong phai tu dung dong ho.
        goi = []

        def cmp_fn(due, at):
            goi.append((due, at))
            return False          # bao "khong tre" du at > due theo dong ho

        act, _ = ar.override_outcome(DUE, SAU, cmp_fn=cmp_fn)
        self.assertEqual(act, ar.ACT_EXCLUDE)
        self.assertEqual(goi, [(DUE, SAU)])


class TestReconcileNguoiDaPhanHoi(unittest.TestCase):
    def test_duyet_tu_choi_va_yeu_cau_bo_sung_deu_la_phan_hoi(self):
        # Nghia vu do PHAN HOI, khong do DONG Y. Cham theo ket qua duyet se bien
        # SLA thanh ap luc phai duyet.
        for st in ("Approved", "Rejected", "Information Requested"):
            act, closed, _ = ar.reconcile_decision("In Progress", st, TRUOC)
            self.assertEqual((act, closed), (ar.ACT_CLOSE, TRUOC), st)

    def test_lay_dung_moc_da_bam_chu_khong_phai_bay_gio(self):
        act, closed, _ = ar.reconcile_decision("Approved", "Approved", SAU)
        self.assertEqual(closed, SAU)


class TestReconcileNguoiChuaBam(unittest.TestCase):
    def test_cap_con_chay_thi_con_no(self):
        act, closed, reason = ar.reconcile_decision("In Progress", "Pending", None)
        self.assertEqual((act, closed, reason), (ar.ACT_OPEN, None, None))

    def test_cap_da_dong_thi_nguoi_khac_da_xu_ly(self):
        for lv in ("Approved", "Rejected"):
            act, _, reason = ar.reconcile_decision(lv, "Pending", None)
            self.assertEqual(act, ar.ACT_EXCLUDE, lv)
            self.assertEqual(reason, ar.REASON_ANY_ONE)

    def test_nguoi_bi_skipped_luon_duoc_loai_tru(self):
        # CO Y khong nghiem hon duong hook: duong chay bu khong biet chac vi sao
        # mot nguoi bi Skipped, nen no chon nhanh khong cham diem.
        act, _, reason = ar.reconcile_decision("Approved", "Skipped", None)
        self.assertEqual((act, reason), (ar.ACT_EXCLUDE, ar.REASON_ANY_ONE))


class TestReconcileCapBiBoQua(unittest.TestCase):
    def test_cap_skipped_thi_khong_tao_ban_ghi_nao(self):
        # Trung nguoi duyet -> cap bi bo qua tu luc nop. Khong ai no gi ca.
        for st in ("Pending", "Approved", "Skipped"):
            act, _, _ = ar.reconcile_decision("Skipped", st, None)
            self.assertEqual(act, ar.ACT_SKIP, st)


class TestReconcileTrangThaiLa(unittest.TestCase):
    def test_trang_thai_khong_ro_thi_bo_qua_va_noi_ra(self):
        # Approval Center co the them trang thai moi ma khong ai bao. Doan bua o
        # day se tao ra nhung vet tre khong co that.
        act, _, reason = ar.reconcile_decision("In Progress", "Delegated", None)
        self.assertEqual(act, ar.ACT_SKIP)
        self.assertIn("Delegated", reason)


if __name__ == "__main__":
    unittest.main()
