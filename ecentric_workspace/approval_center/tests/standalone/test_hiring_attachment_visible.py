# Copyright (c) 2026, eCentric and contributors
"""Tep da tai len phai NHIN THAY duoc tren form Tuyen dung (09/09, Hoan bao).

Tai xong chi hien mot toast roi tat. Du lieu co luu that (`request_attachment` vao state va
van gui kem phieu), nhung:
  * o nhap KHONG duoc ve lai sau khi tai -> dong "Da dinh kem: ..." chi xuat hien neu ve lai
    ca form, tuc phai roi trang roi quay lai;
  * `renderSummary()` KHONG he co dong nao cho tep dinh kem.
Nen man hinh khong con dau vet nao -> nguoi dung tuong tai hong va tai lai.

Bai hoc: "da luu" khong bang "nguoi dung THAY la da luu". Moi duong tai tep phai de lai dau
vet o lai tren man hinh, khong chi mot toast.
"""
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "features")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_SRC = os.path.join(_root(), "approval_center", "features", "hiring_request", "ui",
                    "main_section.html")


def _read():
    return io.open(_SRC, encoding="utf-8").read()


class TestTepHienRaSauKhiTai(unittest.TestCase):
    def test_co_cho_co_dinh_de_ghi_ten_tep(self):
        src = _read()
        self.assertIn('id="hire-file-name"', src,
                      "phai co san mot o de ghi ten tep, khong the ve lai ca form")

    def test_tai_xong_thi_ghi_ten_tep_ngay(self):
        src = _read()
        self.assertIn("function showFileName(", src)
        blk = src[src.index("uploadAttachment(f).then("):]
        blk = blk[:blk.index("\n")]
        self.assertIn("showFileName(url)", blk,
                      "tai xong ma khong ghi ten tep thi man hinh khong con dau vet")

    def test_tom_tat_co_dong_tep_dinh_kem(self):
        src = _read()
        blk = src[src.index("function renderSummary()"):]
        blk = blk[:blk.index("function suggestTitle(")]
        self.assertIn('"Tệp đính kèm"', blk,
                      "Tom tat phai liet ke tep, khong thi tai xong nhin vao khong thay gi")

    def test_hien_TEN_TEP_khong_hien_ca_duong_dan(self):
        """/private/files/HD%20090926_....docx doc khong ra gi; nguoi dung can ten tep."""
        src = _read()
        self.assertIn("function fileLabel(", src)
        blk = src[src.index("function fileLabel("):]
        blk = blk[:blk.index("function showFileName(")]
        self.assertIn("lastIndexOf(", blk)
        self.assertIn("decodeURIComponent", blk, "ten tep co dau bi ma hoa %20 -> phai giai ma")


if __name__ == "__main__":
    unittest.main(verbosity=2)
