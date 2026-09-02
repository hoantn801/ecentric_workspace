# Copyright (c) 2026, eCentric and contributors
"""Ma bam goi khong duoc lech chi vi ho so ky so duoc LUU.

03/09 00:26: p128 luu ho so (them canh Ky chinh) -> `modified` doi -> goi 00030 (khoa 23:06)
lech bam -> anh Lam bam Ky chinh bi chan "Goi tai lieu da thay doi so voi phien ban da khoa".
Lien va Phuong qua duoc truoc do chi vi p127 len TRUOC luc khoa. Cung mot co che.

Ma bam goi ton tai de bat goi bi SUA sau khi khoa: tep, o ky, hinh dang ho so. Duong chuyen
eContract, ghi chu, `modified` - khong doi hinh dang goi. Khoa ho so trong ma bam phai la
khoa CAU TRUC, va bo test nay giu ba dieu:

  1. hashing.profile_structure_key la ham THUAN, on dinh voi modified, nhay voi cau truc.
  2. package.compute_hash khong doc `modified` cua ho so nua.
  3. p129 dong dau lai CA goi CA chan ky chua ket thuc - binding so hai ben voi nhau.
"""
import ast
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from ecentric_workspace.platform.esign.hashing import profile_structure_key  # noqa: E402


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


def _src(*rel):
    return io.open(os.path.join(_ROOT, *rel), encoding="utf-8").read()


_F = {"requester_signature_required": 1, "approver_signature_policy": "All Approval Levels",
      "max_files": 20, "require_signable_pdf": 1}
_L = [{"level_no": i, "requires_signature": 1, "mandatory_placements_per_file": 1}
      for i in (1, 2, 3, 4)]


class TestKhoaCauTrucThuanTuy(unittest.TestCase):
    def test_cung_cau_truc_cung_khoa(self):
        self.assertEqual(profile_structure_key("P", _F, _L), profile_structure_key("P", _F, _L))

    def test_thu_tu_cap_khong_anh_huong(self):
        self.assertEqual(profile_structure_key("P", _F, _L),
                         profile_structure_key("P", _F, list(reversed(_L))))

    def test_khong_co_cho_nao_cho_modified(self):
        """Ham khong nhan `modified` - va do la co y. Neu ai them tham so do vao, test nay
        phai do de nguoi do doc lai vi sao."""
        import inspect
        self.assertEqual(list(inspect.signature(profile_structure_key).parameters),
                         ["profile_name", "fields", "levels"])

    def test_doi_mot_cap_thi_doi_khoa(self):
        lv = [dict(l) for l in _L]
        lv[3]["requires_signature"] = 0
        self.assertNotEqual(profile_structure_key("P", _F, _L), profile_structure_key("P", _F, lv))

    def test_doi_chinh_sach_thi_doi_khoa(self):
        f = dict(_F, approver_signature_policy="Final Level Only")
        self.assertNotEqual(profile_structure_key("P", _F, _L), profile_structure_key("P", f, _L))

    def test_doi_ten_ho_so_thi_doi_khoa(self):
        self.assertNotEqual(profile_structure_key("P", _F, _L), profile_structure_key("Q", _F, _L))

    def test_khoa_co_ten_ho_so_de_doc_duoc(self):
        self.assertTrue(profile_structure_key("PAYMENT-REQUEST-SCTS-UAT", _F, _L)
                        .startswith("PAYMENT-REQUEST-SCTS-UAT@s:"))


class TestComputeHashKhongDocModified(unittest.TestCase):
    def setUp(self):
        self.src = _src("platform", "esign", "package.py")
        self.tree = ast.parse(self.src)

    def _fn(self, name):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.FunctionDef) and n.name == name:
                return n
        raise AssertionError("khong thay " + name)

    def test_compute_hash_goi_profile_structure_key(self):
        goi = {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
               for c in ast.walk(self._fn("compute_hash")) if isinstance(c, ast.Call)}
        self.assertIn("profile_structure_key", goi)

    def test_compute_hash_khong_con_chu_modified(self):
        than = ast.get_source_segment(self.src, self._fn("compute_hash")) or ""
        self.assertNotIn('"modified"', than,
                         "doc `modified` cua ho so vao ma bam = moi lan luu ho so lam moi goi "
                         "dang ky lech - dung loi 03/09 00:26")

    def test_profile_structure_key_trong_package_chi_doc_truong_cau_truc(self):
        than = ast.get_source_segment(self.src, self._fn("profile_structure_key")) or ""
        self.assertNotIn('"modified"', than)
        self.assertNotIn("transitions", than,
                         "duong chuyen eContract khong doi hinh dang goi - dua vao khoa la "
                         "lap lai dung loi vua sua, chi khac ten truong")


class TestP129DongDauLaiCaHaiBen(unittest.TestCase):
    def setUp(self):
        self.src = _src("approval_center", "patches",
                        "p129_restamp_package_hash_structure_key.py")

    def test_dong_dau_ca_chan_ky_chua_ket_thuc(self):
        """binding.py so DSR.package_hash voi goi. Dong dau goi ma quen chan ky = chan ky
        dang bay lap tuc `package_hash_mismatch`."""
        self.assertIn('frappe.db.set_value(DSR, d, "package_hash", moi)', self.src)
        self.assertIn("DSR_TERMINAL", self.src, "chan da ket thuc phai giu dau cu lam lich su")

    def test_chi_goi_dang_ky(self):
        self.assertIn('"status": ["in", ("Locked", "Active")]', self.src)

    def test_ghi_su_kien_truoc_sau(self):
        self.assertIn('"PackageHashRestamped"', self.src)
        self.assertIn('"truoc": r.package_hash', self.src)
        self.assertIn('"sau": moi', self.src)

    def test_verify_doc_lai_va_nem_neu_lech(self):
        sau = self.src.split("# VERIFY")[-1]
        self.assertIn("compute_hash", sau)
        self.assertIn("frappe.throw", sau)


if __name__ == "__main__":
    unittest.main()
