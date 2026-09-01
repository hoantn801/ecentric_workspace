# Copyright (c) 2026, eCentric and contributors
"""Tep dinh kem DOC DUOC bang chu van phai bam duoc.

Tim thay 02/09 khi chay E2E bang tay: dat o chu ky xong thi hien "Khong the luu vi tri chu ky
- thu lai", va console tra ve

    placement_service.py:150  sha = pkgsvc.hashing.sha256_bytes(content)
    hashing.py:18             TypeError: sha256_bytes expects bytes

`File.get_content()` cua Frappe KHONG bao dam tra ve bytes. No doc nhi phan roi THU giai ma:

    self._content = f.read()
    try:
        self._content = self._content.decode()   # tep chu thang o day
    except UnicodeDecodeError:
        pass                                     # .png/.jpg/phan lon .pdf giu nguyen bytes

Phan lon PDF that co luong nen nen giai ma that bai va ve dung bytes - vi vay sau call site
dua thang ket qua vao `sha256_bytes` suot may thang ma khong ai thay gi. Nhung mot chung tu
DOC DUOC - PDF toan ASCII, .txt, .csv, .svg - thi ve `str`, va nguoi dung ket cung o buoc dat
o chu ky voi mot cau bao loi khong noi gi.

Bo test giu ba dieu:

  1. `raw_file_bytes` LUON tra bytes, va bytes do PHAI trung voi tep tren dia. Ma hoa lai
     phai KHONG DOI DU LIEU - neu no doi thi ma bam mo ta mot thu khong ton tai, va toan bo
     chuoi tin cay cua ho so ky sup mot cach im lang. Day la phep kiem quan trong nhat o day.
  2. Kieu la thi NEM, khong bam bua. Bam mot doi tuong khong phai tep = mot ma bam vo nghia
     nhung trong nhu that.
  3. MOI call site trong ma san pham di qua ham nay. Sau cho tung mac cung mot loi; sua nam
     cho trung nhung khong ai buoc cac cho kia phai dung thi lan sau lai co cho thu bay.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_ESIGN = os.path.join(_ROOT, "platform", "esign")


def _read(name):
    return io.open(os.path.join(_ESIGN, name), encoding="utf-8").read()


class _Throw(Exception):
    pass


def _load_package(get_content_returns):
    """Nap package.py THAT voi mot `frappe` gia.

    exec(compile(...)) chu khong phai loader theo duong dan: loader dung lai __pycache__ va
    mot dot bien giu nguyen kich thuoc file se duoc cham tren ban .pyc cu.
    """
    fake = types.ModuleType("frappe")

    class _Doc(object):
        @staticmethod
        def get_content():
            return get_content_returns

    fake.get_doc = lambda dt, name=None: _Doc
    fake.db = types.SimpleNamespace(get_value=lambda *a, **k: "FILE-1")

    def _throw(msg, *a, **k):
        raise _Throw(msg)

    fake._ = lambda s, *a, **k: s
    fake.throw = _throw
    fake.utils = types.SimpleNamespace(now_datetime=lambda: None)
    fake.local = types.SimpleNamespace(response={})
    fake.session = types.SimpleNamespace(user="ai@x.vn")

    stubs = {
        "frappe": fake,
        "frappe.utils": types.SimpleNamespace(now_datetime=lambda: None),
        "ecentric_workspace.platform.esign.events": types.ModuleType("events"),
        "ecentric_workspace.platform.esign.permissions": types.ModuleType("permissions"),
    }
    # `hashing` la module THAT: chinh no la thu tu choi str, nen gia lap no thi bai test tu
    # tra loi lay minh.
    hashing = types.ModuleType("hashing")
    exec(compile(_read("hashing.py"), "hashing.py", "exec"), hashing.__dict__)  # noqa: S102
    stubs["ecentric_workspace.platform.esign.hashing"] = hashing

    pkg = types.ModuleType("ecentric_workspace.platform.esign")
    pkg.events = stubs["ecentric_workspace.platform.esign.events"]
    pkg.hashing = hashing
    pkg.permissions = stubs["ecentric_workspace.platform.esign.permissions"]
    stubs["ecentric_workspace.platform.esign"] = pkg

    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        mod = types.ModuleType("esign_package_under_test")
        exec(compile(_read("package.py"), "package.py", "exec"), mod.__dict__)  # noqa: S102
        mod._hashing_that = hashing
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


#: Byte that tren dia. Toan ASCII -> Frappe giai ma duoc -> tra ve `str`. Dung tinh huong
#: da lam ket buoc dat o chu ky.
_PDF_ASCII = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
#: PDF co byte nhi phan -> khong giai ma duoc -> Frappe tra ve bytes.
_PDF_NHIPHAN = b"%PDF-1.4\n\x80\x81\xfe\xff stream binary\n%%EOF\n"
#: Chung tu chu CO DAU tieng Viet. Bat buoc phai co mot mau khong-phai-ASCII: voi noi dung
#: thuan ASCII thi utf-8 va latin-1 cho ra byte y het nhau, nen mot ban ma hoa lai SAI BANG
#: van xanh. Da that su song sot mot vong dot bien 02/09 truoc khi them mau nay.
_TXT_TIENG_VIET = "Chứng từ thanh toán – phí dịch vụ 1.000.000 ₫\n".encode("utf-8")


class TestLuonTraVeBytes(unittest.TestCase):
    def test_tep_giai_ma_duoc_van_ra_bytes(self):
        mod = _load_package(_PDF_ASCII.decode("utf-8"))   # Frappe tra `str`
        self.assertIsInstance(mod.raw_file_bytes("FILE-1"), bytes)

    def test_ma_hoa_lai_KHONG_lam_doi_du_lieu(self):
        """Phep kiem quan trong nhat: ma bam phai mo ta dung tep tren dia."""
        mod = _load_package(_PDF_ASCII.decode("utf-8"))
        self.assertEqual(mod.raw_file_bytes("FILE-1"), _PDF_ASCII,
                         "byte tra ve khac byte tren dia -> ma bam mo ta mot tep khong ton "
                         "tai, va ca chuoi tin cay cua ho so ky hong trong im lang")
        self.assertEqual(
            mod._hashing_that.sha256_bytes(mod.raw_file_bytes("FILE-1")),
            mod._hashing_that.sha256_bytes(_PDF_ASCII),
            "ma bam phai trung voi ma bam cua chinh tep goc")

    def test_chung_tu_co_dau_tieng_viet_quay_ve_nguyen_ven(self):
        """Chan ban ma hoa lai sai bang.

        Chung tu thuc te o day co dau. Neu ai do doi `encode("utf-8")` sang mot bang khac
        thi hoac no nem, hoac no tra ra byte khac - ca hai deu lam ma bam mo ta sai tep.
        Mau ASCII o cac phep kiem tren KHONG bat duoc dieu nay.
        """
        mod = _load_package(_TXT_TIENG_VIET.decode("utf-8"))
        self.assertEqual(mod.raw_file_bytes("FILE-1"), _TXT_TIENG_VIET,
                         "phai ma hoa lai bang DUNG bang ma Frappe da dung de giai ma")

    def test_tep_nhi_phan_giu_nguyen(self):
        mod = _load_package(_PDF_NHIPHAN)
        self.assertEqual(mod.raw_file_bytes("FILE-1"), _PDF_NHIPHAN,
                         "duong cu (bytes) khong duoc dong vao")

    def test_kieu_la_thi_NEM_chu_khong_bam_bua(self):
        for xau in (None, 123, {"a": 1}):
            mod = _load_package(xau)
            with self.assertRaises(_Throw, msg="kieu %r phai bi tu choi" % type(xau)):
                mod.raw_file_bytes("FILE-1")

    def test_file_bytes_cung_di_qua_duong_nay(self):
        mod = _load_package(_PDF_ASCII.decode("utf-8"))
        self.assertEqual(mod.file_bytes("DSF-1"), _PDF_ASCII)


class TestMoiNoiGoiDeuDiQuaHamNay(unittest.TestCase):
    """Sau cho tung mac cung mot loi. Sua mot cho ma khong buoc nam cho kia la de lai lan sau."""

    #: `api.py` tra thang tep ve trinh duyet, khong bam - co y KHONG nam trong danh sach.
    FILE_MA_SAN_PHAM = ("document_setup.py", "lifecycle.py", "placement_service.py",
                        "requester.py", "package.py")

    def test_khong_file_nao_con_goi_get_content_truc_tiep(self):
        for name in self.FILE_MA_SAN_PHAM:
            src = _read(name)
            goi = [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "get_content"]
            gioi_han = 1 if name == "package.py" else 0
            self.assertLessEqual(
                len(goi), gioi_han,
                "%s con goi File.get_content() truc tiep (%d cho). `get_content()` tra `str` "
                "cho tep giai ma duoc -> sha256_bytes nem TypeError. Phai di qua "
                "package.raw_file_bytes." % (name, len(goi)))

    def test_cac_file_kia_that_su_goi_raw_file_bytes(self):
        """Chan cach: xoa sach loi goi cung lam phep kiem tren xanh."""
        for name in ("document_setup.py", "lifecycle.py", "placement_service.py",
                     "requester.py"):
            src = _read(name)
            goi = [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "attr", None) == "raw_file_bytes"]
            self.assertTrue(goi, "%s khong con doc byte tep qua raw_file_bytes - hoac da bi "
                                 "go mat, hoac da quay ve get_content()" % name)

    def test_ham_dung_chung_van_ton_tai_va_ep_kieu(self):
        src = _read("package.py")
        fn = next((n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.FunctionDef) and n.name == "raw_file_bytes"), None)
        self.assertIsNotNone(fn, "raw_file_bytes bien mat")
        than = ast.get_source_segment(src, fn) or ""
        self.assertIn('encode("utf-8")', than,
                      "phai ma hoa lai bang UTF-8 - dung phep giai ma ma Frappe da dung, "
                      "nen byte quay ve nguyen ven")
        self.assertIn("frappe.throw", than, "kieu la phai nem, khong duoc bam bua")


if __name__ == "__main__":
    unittest.main()
