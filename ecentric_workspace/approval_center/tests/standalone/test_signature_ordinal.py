# Copyright (c) 2026, eCentric and contributors
"""Chan thu N cua mot nguoi doi chu ky thu N+1 cua nguoi do - DEM, khong so gio.

Hai ca that, ca hai phai dung cung luc:

  28/08 23:53 - nguoi trinh ky. 23:54:01 chan duyet cap 1 cua CHINH NGUOI DO xep hang.
  Tai lieu co MOT chu ky cua ho. Chan duyet KHONG duoc dong - chu ky do la cua chan truoc.

  02/09 23:06 - nguoi trinh ky roi duyet cap 1 trong cung mot phut. eContract tra
  `signed_at` toi PHUT nen ca hai chu ky deu doc thanh 23:06:00. Tai lieu co HAI chu ky.
  Chan duyet PHAI dong - chu ky thu hai la cua no, du khong phan biet duoc bang gio.

San thoi gian cu dung ca 1 nhung hong ca 2 (23:06:00 "cu hon" moc 23:06:2x). Thu tu dung
ca hai. Bo test nay chay code THAT cua providers/base.py, khong stub.
"""
import os
import sys
import unittest
from datetime import datetime

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from ecentric_workspace.platform.esign.providers.base import (  # noqa: E402
    NormalizedDocState, SignatureProviderAdapter)

DOC = "8e912015-aaaa-bbbb-cccc-000000000002"
HOAN = "hoan.tran@ecentric.vn"
LIEN = "lien.vu@ecentric.vn"


def _state(signers):
    return NormalizedDocState(DOC, "processing", signers=signers,
                              files=[{"file_id": "f1", "name": "Invoice.pdf"}])


def _signer(email=HOAN, status="signed", signed_at="02/09/2026 23:06"):
    return {"user_id": None, "signature_id": None, "email": email, "display_name": "x",
            "status": status, "signed_at": signed_at, "is_external": False}


def _expected(prior, signed_after=None):
    out = {"document_id": DOC, "user_id": "73f72e15", "email": HOAN, "file_count": 1,
           "prior_signatures": prior}
    if signed_after is not None:
        out["signed_after"] = signed_after
    return out


def _verify(signers, expected):
    return SignatureProviderAdapter.verify_signed_result(_state(signers), expected)


class TestCa_02_09_CungPhut(unittest.TestCase):
    """Hai chu ky cung phut, chan thu hai phai dong."""

    def test_chan_thu_hai_dong_khi_co_hai_chu_ky_cung_phut(self):
        # cua so: hoi luc 23:06:29, tru dung sai 120s -> 23:04:29
        res = _verify([_signer(), _signer(), _signer(email=LIEN, status="pending")],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 23, 4, 29)))
        self.assertTrue(res.ok, res.reason)

    def test_chan_dau_tien_dong_khi_co_mot_chu_ky(self):
        res = _verify([_signer()], _expected(prior=0, signed_after=datetime(2026, 9, 2, 23, 4, 0)))
        self.assertTrue(res.ok, res.reason)


class TestCa_28_08_ChuKyCuaChanTruoc(unittest.TestCase):
    """Mot chu ky, chan thu hai KHONG duoc dong - cai co la cua chan trinh ky."""

    def test_chan_thu_hai_tu_choi_khi_chi_co_mot_chu_ky(self):
        res = _verify([_signer(signed_at="28/08/2026 23:53")],
                      _expected(prior=1, signed_after=datetime(2026, 8, 28, 23, 52, 1)))
        self.assertFalse(res.ok)
        self.assertTrue(res.reason.startswith("not_enough_signatures:have=1/need=2"),
                        res.reason)

    def test_ly_do_noi_ro_thieu_bao_nhieu(self):
        res = _verify([_signer()], _expected(prior=2))
        self.assertEqual(res.reason, "not_enough_signatures:have=1/need=3")


class TestThuTuLaCuaNguoiNay_KhongTinhNguoiKhac(unittest.TestCase):
    def test_chu_ky_cua_nguoi_khac_khong_dem_vao(self):
        # Lien da ky, Hoan moi ky mot lan; chan thu hai cua Hoan van thieu.
        res = _verify([_signer(email=LIEN), _signer()],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 23, 4, 0)))
        self.assertFalse(res.ok)
        self.assertIn("not_enough_signatures", res.reason)

    def test_dong_pending_khong_dem(self):
        res = _verify([_signer(), _signer(status="pending")],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 23, 4, 0)))
        self.assertFalse(res.ok)
        self.assertIn("not_enough_signatures", res.reason)


class TestCuaSoThoiGianVanCon(unittest.TestCase):
    """Thu tu thay SAN, khong thay CUA SO. Chu ky lam TRUOC khi hoi van bi tu choi."""

    def test_chu_ky_thu_N_cu_hon_cua_so_thi_tu_choi(self):
        # Hai chu ky luc 10:00; chan thu hai hoi luc 15:00 -> cua so 14:58. Chu ky thu hai
        # (10:00) cu hon cua so -> khong phai cua chan nay.
        res = _verify([_signer(signed_at="02/09/2026 10:00"), _signer(signed_at="02/09/2026 10:00")],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 14, 58)))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)

    def test_chu_ky_cu_cua_chan_truoc_ngoai_cua_so_khong_lam_hong_chan_nay(self):
        # Trinh ky 10:00 (ngoai cua so), duyet 15:00:30 (trong cua so). Xep tang dan:
        # [10:00, 15:00]; chan thu hai lay 15:00 -> dat.
        res = _verify([_signer(signed_at="02/09/2026 15:00"), _signer(signed_at="02/09/2026 10:00")],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 14, 58)))
        self.assertTrue(res.ok, res.reason)


class TestKhongBietThuTuThiGiuDuongCu(unittest.TestCase):
    """`prior_signatures` = None (khong dem duoc) KHONG duoc coi la 0."""

    def test_None_di_duong_cu_bat_ky_dong_nao(self):
        exp = _expected(prior=None, signed_after=datetime(2026, 9, 2, 23, 4, 0))
        exp.pop("prior_signatures")
        exp["prior_signatures"] = None
        res = _verify([_signer()], exp)
        self.assertTrue(res.ok, "duong cu: mot dong dat moi dieu kien la du")

    def test_gio_khong_doc_duoc_thi_that_bai_dong(self):
        res = _verify([_signer(signed_at="luc nay"), _signer()],
                      _expected(prior=1, signed_after=datetime(2026, 9, 2, 23, 4, 0)))
        self.assertFalse(res.ok)
        self.assertIn("signed_at_unreadable", res.reason)


if __name__ == "__main__":
    unittest.main()
