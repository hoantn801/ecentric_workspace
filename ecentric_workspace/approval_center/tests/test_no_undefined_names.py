# Copyright (c) 2026, eCentric and contributors
"""Cong chan: khong module Python nao duoc dung mot TEN CHUA DINH NGHIA.

VI SAO CO FILE NAY (15/09). Luc chuyen `sharepoint_sync.py` sang
`shared/integrations/sharepoint_mirror.py`, phan dau file duoc viet lai va dong
`from frappe.utils import now_datetime` roi mat. Python khong noi gi luc nap module - no chi
nem `NameError` LUC CHAY, ma dong do nam trong mot viec chay nen sau khi nguoi dung da gui
phieu xong. Ket qua: EC-CTR-2026-00014 tai duoc ca hai tep len SharePoint roi chet o buoc luu
lien ket, va tren man hinh chi thay the dinh kem ghi "Mo" thay vi "Mo online" - khong mot dau
hieu nao chi ra nguyen nhan.

Te hon: bo test cua chinh module do van XANH, vi no `exec` mot doan cat ra khoi file roi TU
TIEM `now_datetime` vao khong gian ten. Phep kiem tu cap cho minh thu ma ban that khong co.
Xem [[feedback-test-asserting-call-exists-proves-nothing]] - cung ho: mot phep kiem chi do
chinh cai gia no dung len.

CACH DO: `pyflakes` - no phan giai pham vi that (import, tham so, bien cuc bo, comprehension,
except-as, global) nen khong phai tu che lai mot bo phan tich nua roi sai kieu khac.

KHONG CHAY DUOC != HONG. Thieu pyflakes thi ma thoat 2 kem huong dan cai, dung le nha
(`run_js.sh` da tra gia cho bai hoc nay: mot bao cao khong phan biet duoc "hong" voi "chua
chay" se day nguoi ta bo qua ket qua).
"""
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _app_root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


APP = _app_root()

#: Nhung cho pyflakes bao "undefined" MA KHONG PHAI LOI - moi dong kem ly do.
BO_QUA = (
    # Nguon Server Script cua Frappe: sandbox tiem san `frappe`, `doc`, `_`... luc chay.
    # Chung khong bao gio duoc import nhu module Python binh thuong.
    ("server_scripts/", None),
    # `globals().update(bind(...))` bom ham vao module luc nap - pyflakes khong theo duoc.
    ("approval_center/api/", None),
    ("approval_center/features/payment_request/controllers/api.py", None),
)


#: DA BIET, CHUA SUA - thuoc pham vi cua dot/chat khac (luat cua Hoan: viec khong phai cua
#: minh thi BAO, khong tu sua). De o day thi cong van XANH hom nay va do ngay khi co cai MOI -
#: mot cong do san tu ngay dau se bi lo, va lo mot lan la lo mai. Cung khuon voi
#: `test_no_mojibake.py :: test_known_unfixed_list_does_not_rot`.
#:
#: Ca hai deu la NameError THAT luc chay, khong phai bao dong gia:
#:   * api_brands.py    : file chi `import frappe`, khong co `from frappe import _`
#:   * ai_topup/...     : `commit` khong duoc dinh nghia o dau trong module
DA_BIET_CHUA_SUA = (
    ("alerts/api_brands.py", "undefined name '_'"),
    ("approval_center/features/ai_topup/infrastructure/activation.py", "undefined name 'commit'"),
)


def _da_biet(dong):
    for duong, ten in DA_BIET_CHUA_SUA:
        if duong in dong and ten in dong:
            return (duong, ten)
    return None


def _bo_qua(dong):
    for phan, _ly_do in BO_QUA:
        if phan in dong:
            return True
    return False


class TestKhongCoTenChuaDinhNghia(unittest.TestCase):
    def test_pyflakes_khong_bao_undefined_name(self):
        try:
            import pyflakes  # noqa: F401
        except ImportError:
            print("KHONG CHAY DUOC: thieu pyflakes. Cai bang:")
            print("    pip install pyflakes --break-system-packages")
            print("  Day KHONG phai test hong - chua kiem duoc dong nao.")
            sys.exit(2)

        out = subprocess.run([sys.executable, "-m", "pyflakes", APP],
                             capture_output=True, text=True).stdout
        tat_ca = [d for d in out.splitlines()
                  if "undefined name" in d and not _bo_qua(d)]
        loi = [d for d in tat_ca if not _da_biet(d)]
        # Con so nay chi de biet phep do CON SONG. Neu no ve 0 vi quet nham thu muc thi
        # bai test se xanh ma khong kiem gi - dung kieu "bo test chet am tham" da gap.
        so_file = sum(len([f for f in fs if f.endswith(".py")]) for _, _, fs in os.walk(APP))
        self.assertGreater(so_file, 200, "quet duoc qua it file Python - phep do hong, khong phai ma sach")
        self.assertEqual([], loi, "co ten chua dinh nghia -> NameError luc chay:\n  " + "\n  ".join(loi))

    def test_luoi_bo_qua_khong_nuot_nham_vung_dang_kiem(self):
        """BO_QUA phai HEP. Noi rong no la cach de nhat de lam ca cong nay vo hieu ma van xanh.

        Do bang chinh hai muc trong DA_BIET_CHUA_SUA: chung la loi THAT trong vung dang kiem,
        nen `_bo_qua` phai tra ve False cho chung. Neu ai do them mot muc rong kieu
        "ecentric_workspace/" vao BO_QUA thi hai phep kiem nay do ngay."""
        for duong, ten in DA_BIET_CHUA_SUA:
            dong = "%s/%s:1:1: %s" % (APP, duong, ten)
            self.assertFalse(_bo_qua(dong),
                             "BO_QUA dang nuot ca %s - luoi qua rong, cong thanh vo hieu" % duong)

    def test_danh_sach_da_biet_khong_muc_nat(self):
        """Muc nao trong DA_BIET_CHUA_SUA da duoc sua thi phai GO khoi danh sach.

        Khong co phep kiem nay thi danh sach cu dai ra va che mat cac lan tai pham sau do -
        dung y nhu `test_no_mojibake` da hoc duoc."""
        try:
            import pyflakes  # noqa: F401
        except ImportError:
            self.skipTest("thieu pyflakes")
        out = subprocess.run([sys.executable, "-m", "pyflakes", APP],
                             capture_output=True, text=True).stdout
        con = [d for d in out.splitlines() if "undefined name" in d]
        da_sua = [(duong, ten) for duong, ten in DA_BIET_CHUA_SUA
                  if not any(duong in d and ten in d for d in con)]
        self.assertEqual([], da_sua,
                         "da duoc sua roi - GO khoi DA_BIET_CHUA_SUA: %s" % (da_sua,))


if __name__ == "__main__":
    unittest.main(verbosity=1)
