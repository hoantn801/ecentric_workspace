# Copyright (c) 2026, eCentric and contributors
"""Nguoi xu ly phai TAI LEN duoc tep ket qua (08/09).

`/api/method/upload_file` co kem `doctype` + `docname` thi Frappe kiem quyen GHI tren chinh
ho so. Ca sau DocType fulfillment deu chi cho System Manager ghi (rieng EC Asset Request co
them EC Ops System), trong khi nguoi xu ly that - Dong, Linh Vuong, Thuong, Tuan - khong ai
co System Manager. Ket qua: 5/6 form khong ai tai duoc tep ket qua, chi hien "Loi tai" tron.

Cach dung (Payment Request lam tu dau, khong he dinh): tai len KHONG kem doctype/docname ->
file mo coi; server gan vao ho so luc hoan tat qua `attach_extra_files`, tuc duong da kiem
quyen san (chi nguoi da nhan xu ly hoac quan tri).

Bo test giu ba dieu:
  1. KHONG form nao gui doctype/docname khi upload. Tran = 0, chi duoc phep giu 0.
  2. Form nao co complete_fulfillment thi PHAI goi attach_extra_files - neu khong, file tai
     len se khong bao gio hien ra o muc "Dinh kem".
  3. Loi tai phai noi RO LY DO. "Loi tai" tron chinh la thu khien ca nay phai cho toi khi
     nguoi dung chup man hinh gui len moi biet la 403.
"""
import io
import os
import re
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


_ROOT = _root()
_FEATS = os.path.join(_ROOT, "approval_center", "features")


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _features():
    return sorted(f for f in os.listdir(_FEATS)
                  if os.path.isfile(os.path.join(_FEATS, f, "ui", "main_section.html")))


class TestUploadKhongGuiDoctype(unittest.TestCase):
    def test_khong_form_nao_gui_doctype_docname_khi_upload(self):
        pham = []
        for feat in _features():
            src = _read(os.path.join(_FEATS, feat, "ui", "main_section.html"))
            if "upload_file" not in src:
                continue
            if 'fd.append("doctype"' in src or 'fd.append("docname"' in src:
                pham.append(feat)
        self.assertEqual(
            pham, [],
            "cac form nay van gui doctype/docname -> Frappe se doi quyen GHI tren ho so, "
            "nguoi xu ly khong phai System Manager se khong tai duoc tep: %s" % pham)


class TestServerGanFile(unittest.TestCase):
    def test_moi_complete_fulfillment_deu_gan_file_vao_ho_so(self):
        thieu = []
        for feat in _features():
            svc = os.path.join(_FEATS, feat, "application", "service.py")
            if not os.path.isfile(svc):
                continue
            src = _read(svc)
            if "def complete_fulfillment" not in src:
                continue
            if "attach_extra_files" not in src:
                thieu.append(feat)
        self.assertEqual(
            thieu, [],
            "tai len khong kem doctype/docname thi file la mo coi; khong goi attach_extra_files "
            "thi no khong bao gio hien o muc Dinh kem: %s" % thieu)

    def test_gan_file_TRUOC_khi_save(self):
        """Gan sau khi save thi hook attach_files_to_document cua Frappe da chay xong ->
        de sinh dong dinh kem thu hai (da tung dinh voi phieu khac)."""
        for feat in _features():
            svc = os.path.join(_FEATS, feat, "application", "service.py")
            if not os.path.isfile(svc):
                continue
            src = _read(svc)
            if "def complete_fulfillment" not in src or "attach_extra_files" not in src:
                continue
            seg = src[src.index("def complete_fulfillment"):]
            nxt = seg.find("\ndef ", 1)
            seg = seg[:nxt] if nxt > 0 else seg
            i_at = seg.find("attach_extra_files(doc")
            i_sv = seg.find("doc.save(")
            self.assertGreater(i_at, 0, "%s: khong thay loi goi attach_extra_files" % feat)
            self.assertGreater(i_sv, 0, "%s: khong thay doc.save" % feat)
            self.assertLess(i_at, i_sv, "%s: phai gan file TRUOC doc.save" % feat)


class TestBaoLoiRoRang(unittest.TestCase):
    def test_khong_con_bao_loi_tai_tron(self):
        """Nhanh loi cua upload phai di qua mapErr de hien ly do that tu server."""
        for feat in _features():
            p = os.path.join(_FEATS, feat, "ui", "main_section.html")
            src = _read(p)
            if "upload_file" not in src:
                continue
            if 'textContent="Lỗi tải"' in src:
                self.fail("%s: van bao 'Loi tai' tron, khong noi ly do that (vd 403 thieu quyen)"
                          % feat)

    #: Sau form co buoc xu ly - pham vi dot sua 08/09.
    FULFILLMENT_FORMS = ("ai_topup", "asset_request", "data_request", "document_request",
                         "resignation", "system_request")

    def test_upload_o_buoc_xu_ly_co_bat_413(self):
        """Tep qua lon tra 413 KHONG kem JSON; khong bat rieng thi nguoi dung thay loi vo nghia.

        Chi chot cho o tai len o BUOC XU LY (pham vi dot nay). Nhieu form khac van con thieu
        o duong tai len cua NGUOI DE NGHI - no khac ca ve ma lan ve nguoi dung, sua chung mot
        the se thanh mot dot rat rong; ghi lai day de khong quen."""
        for feat in self.FULFILLMENT_FORMS:
            src = _read(os.path.join(_FEATS, feat, "ui", "main_section.html"))
            self.assertIn("413", src, "%s: chua xu ly 413 (tep qua lon)" % feat)


class TestDocumentRequestKhongConSaiDoctype(unittest.TestCase):
    def test_document_request_khong_con_tro_vao_EC_Data_Request(self):
        """Truoc day document_request upload voi doctype 'EC Data Request' - chep nham.
        Bo doctype la het, nhung chot lai de khong ai chep nham lan nua."""
        src = _read(os.path.join(_FEATS, "document_request", "ui", "main_section.html"))
        self.assertNotIn("EC Data Request", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
