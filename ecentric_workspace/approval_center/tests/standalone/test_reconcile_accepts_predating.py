# Copyright (c) 2026, eCentric and contributors
"""Doi soat THU CONG chap nhan chu ky co truoc luc ERP gui lenh - va chi the thoi.

KICH BAN THAT (09/09/2026, phieu EC-PAYR-2026-00053, chan ky EC-DSR-2026-00080).
Nguoi trinh ky gui luc 08/09 23:25. SCTS gui mail. Nguoi duyet (Vinh) vao THANG cong
ky tay luc 23:48. Sang hom sau ho bam Duyet tren ERP; ERP gui lenh ky luc 11:19, SCTS
khong con gi de ky nen nhan roi im, va chan ky nam Manual Review voi
`signature_predates_request:08/09/2026 23:48`.

Chu ky LA THAT, dung nguoi, dung tai lieu. Hai lop bao ve dang BAT DONG:
  * phep DEM (`prior_signatures`, 02/09) noi: day dung la chu ky thu 1 cua nguoi nay,
    ma chan nay can chu ky thu 1 -> hop le;
  * moc THOI GIAN (`signed_after`, 27/08) noi: 23:48 < 11:17 -> tu choi.
Lop cu dang chan dung cai chu ky ma lop moi xac nhan la that.

BA rang buoc cua ban sua, va bo test nay giu ca ba:
  1. Duong TU DONG khong doi gi - khong co co thi van tu choi y nhu truoc.
  2. Co chi song trong nhanh co phep DEM. Khong dem duoc (prior=None) thi khong co duong
     nao toi day: luc do moc thoi gian la lop bao ve DUY NHAT, bo no la bo het.
  3. Cac phep tu choi KHAC (sai nguoi, chua ky, sai tai lieu, khong du chu ky) van tu
     choi nguyen ven - co nay chi bo qua DUNG mot ly do.
Va: ket qua di duong nay mang mot ly do RIENG de con dem duoc, khong lan voi "verified".
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


def _base():
    """Nap providers/base.py voi frappe gia (module co `import frappe` o dau)."""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.utils = types.ModuleType("frappe.utils")
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = fk
    sys.modules["frappe.utils"] = fk.utils
    try:
        mod = types.ModuleType("base_under_test")
        exec(compile(_read("platform", "esign", "providers", "base.py"), "base.py", "exec"),
             mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


_B = _base()
_DOC = "74769fab"
_WHO = "vinh.vu@ecentric.vn"


def _state(signers):
    return _B.NormalizedDocState(document_id=_DOC, status="processing",
                                 files=[], signers=signers, raw={})


def _signer(email=_WHO, status="signed", signed_at="08/09/2026 23:48"):
    return {"email": email, "status": status, "signed_at": signed_at,
            "user_id": None, "signature_id": None, "role": "thamgia"}


def _expected(**kw):
    from datetime import datetime
    base = {"document_id": _DOC, "user_id": None, "email": _WHO,
            # ERP hoi luc 11:17 sang hom sau (11:19 tru dung sai 120 giay)
            "signed_after": datetime(2026, 9, 9, 11, 17, 0),
            "prior_signatures": 0}
    base.update(kw)
    return base


class TestDuongTuDongKhongDoi(unittest.TestCase):
    """Ve an toan: khong bat co thi hanh vi y het truoc ban sua."""

    def test_khong_co_co_thi_van_TU_CHOI_chu_ky_co_truoc(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected())
        self.assertFalse(res.ok)
        self.assertTrue(res.reason.startswith("signature_predates_request"), res.reason)

    def test_co_tat_tuong_minh_cung_tu_choi(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected(allow_predating=False))
        self.assertFalse(res.ok)


class TestDoiSoatThuCong(unittest.TestCase):
    def test_bat_co_thi_chap_nhan_va_NOI_RO_da_di_duong_nao(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected(allow_predating=True))
        self.assertTrue(res.ok, res.reason)
        self.assertTrue(res.reason.startswith("verified_predating_manual"), res.reason)
        self.assertIn("23:48", res.reason, "giu lai gio ky de con doi chieu voi cong")
        self.assertNotEqual(res.reason, "verified",
                            "phai phan biet duoc voi xac minh thuong de con dem")

    def test_chu_ky_MOI_hon_van_ra_verified_thuong(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="09/09/2026 11:20")]),
            _expected(allow_predating=True))
        self.assertTrue(res.ok)
        self.assertEqual(res.reason, "verified", "duong binh thuong khong duoc doi nhan")


class TestCoKHONGMoRongSangCacLoiKHAC(unittest.TestCase):
    """Co nay chi duoc bo qua DUNG mot ly do. Moi ly do tu choi khac phai nguyen ven."""

    def test_van_tu_choi_khi_nguoi_ky_khong_co_tren_tai_lieu(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer(email="ai.do@ec.vn")]), _expected(allow_predating=True))
        self.assertFalse(res.ok)
        self.assertIn("expected_signer_absent", res.reason)

    def test_van_tu_choi_khi_CHUA_ky(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer(status="pending", signed_at=None)]),
            _expected(allow_predating=True))
        self.assertFalse(res.ok)

    def test_van_tu_choi_khi_KHONG_DU_chu_ky(self):
        """Chan thu 2 cua mot nguoi ma tai lieu moi co 1 chu ky - dung lop loi 28/08
        (cap duyet dong bang chu ky trinh ky cua chinh nguoi do). Co nay KHONG duoc pha."""
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected(prior_signatures=1, allow_predating=True))
        self.assertFalse(res.ok)
        self.assertIn("not_enough_signatures", res.reason)

    def test_van_tu_choi_khi_sai_tai_lieu(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected(document_id="khac", allow_predating=True))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "document_id_mismatch")

    def test_van_tu_choi_khi_SAI_MAU_CHU_KY_du_da_moi_hon(self):
        """Phep tu choi nay xay ra o DUNG cho ma co dang can thiep (_check_one_signer),
        nhung KHONG phai ly do predating. Neu co bo qua ca no thi mot chu ky bang mau
        khac cua cung nguoi cung dong duoc cap - da tu thu dot bien va no SONG SOT."""
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([dict(_signer(signed_at="09/09/2026 11:20"), signature_id="mau-B")]),
            _expected(signature_id="mau-A", allow_predating=True))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "signature_id_mismatch")

    def test_van_tu_choi_khi_SAI_MAU_CHU_KY_va_ky_truoc(self):
        """Ca hai loi cung luc: co chi duoc xoa loi thoi gian, khong xoa loi mau chu ky."""
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([dict(_signer(), signature_id="mau-B")]),
            _expected(signature_id="mau-A", allow_predating=True))
        self.assertFalse(res.ok)

    def test_van_tu_choi_khi_gio_ky_khong_doc_duoc(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="hom qua")]), _expected(allow_predating=True))
        self.assertFalse(res.ok)
        self.assertIn("signed_at_unreadable", res.reason)


class TestCoKHONGSongNgoaiNhanhDEM(unittest.TestCase):
    """Rang buoc quan trong nhat. Khong dem duoc (prior=None) thi moc thoi gian la lop
    bao ve DUY NHAT con lai - co KHONG duoc co tac dung o do."""

    def test_prior_None_thi_co_VO_HIEU(self):
        res = _B.SignatureProviderAdapter.verify_signed_result(
            _state([_signer()]), _expected(prior_signatures=None, allow_predating=True))
        self.assertFalse(res.ok, "khong dem duoc ma van cho qua = bo het bao ve")
        self.assertTrue(res.reason.startswith("signature_predates_request"), res.reason)


class TestDuongGoiTuTrenXuong(unittest.TestCase):
    """Co phai di duoc tu API xuong, va CHI tu duong doi soat thu cong."""

    def test_api_nhan_tham_so_va_chuyen_xuong_service(self):
        src = _read("platform", "esign", "api.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "reconcile_signature_request")
        self.assertIn("assert_system_manager", fn, "chi System Manager duoc bam")
        # Phai CHUYEN TIEP that su. Chi kiem "co goi reconcile_manual_review" thi bo tham
        # so di van xanh - da tu thu dot bien va no SONG SOT: API nhan co roi nuot mat.
        self.assertIn("reconcile_manual_review(dsr_name, accept_predating=", fn)

    def test_service_chuyen_tiep_vao_expected(self):
        src = _read("platform", "esign", "service.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "reconcile_manual_review")
        self.assertIn("allow_predating=accept_predating", fn)
        self.assertIn("accept_predating", fn)

    def test_DUONG_TU_DONG_khong_he_nhac_toi_co(self):
        """tasks.py la duong poll tu dong. No KHONG duoc truyen co nay."""
        src = _read("platform", "esign", "tasks.py")
        self.assertNotIn("allow_predating", src)
        self.assertNotIn("accept_predating", src)

    def test_mac_dinh_la_TAT(self):
        src = _read("platform", "esign", "service.py")
        self.assertIn("def reconcile_manual_review(dsr_name, accept_predating=False)", src)
        self.assertIn("def _expected_for(dsr, allow_predating=False)", src)

    def test_expected_lay_co_TU_THAM_SO_chu_khong_phai_hang_so(self):
        """`"allow_predating": True` cung qua duoc phep kiem chu ky ham o tren, nhung no
        bat co cho MOI duong - ke ca poll tu dong. Da tu thu dot bien: SONG SOT.
        Nen chot han bieu thuc: gia tri phai DAN toi chinh tham so."""
        src = _read("platform", "esign", "service.py")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_expected_for")
        found = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "allow_predating":
                        found = ast.unparse(v)
        self.assertIsNotNone(found, "khong thay khoa allow_predating trong _expected_for")
        self.assertIn("allow_predating", found,
                      "gia tri phai lay tu THAM SO, khong duoc la hang so: %s" % found)
        self.assertNotIn("True", found)


if __name__ == "__main__":
    unittest.main()
