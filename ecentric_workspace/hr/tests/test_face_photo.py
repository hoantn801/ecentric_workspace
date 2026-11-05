# Copyright (c) 2026, eCentric and contributors
"""/khuon-mat (ec-face-photo-v1): anh nhan vien -> JPG <= 200 KB, ten "Ma_Ten.jpg" khop ERP.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_face_photo
"""
import io
import os
import unittest

from ecentric_workspace.hr.face_photo import constants as C
from ecentric_workspace.hr.face_photo import imaging, naming

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _jpg(w, h, noise=True):
    from PIL import Image
    import random
    img = Image.new("RGB", (w, h), (200, 180, 160))
    if noise:   # anh nhieu chi tiet -> kho nen, giong anh dien thoai that
        px = img.load()
        rnd = random.Random(1)
        for x in range(0, w, 2):
            for y in range(0, h, 2):
                px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


class TestImaging(unittest.TestCase):
    def test_anh_lon_nhieu_chi_tiet_nen_duoi_200kb(self):
        out, size = imaging.prepare(_jpg(3000, 4000))
        self.assertLessEqual(len(out), C.TARGET_BYTES)
        self.assertLessEqual(max(size), C.MAX_SIDE)
        self.assertEqual(out[:2], b"\xff\xd8")          # JPEG

    def test_anh_qua_nho_bao_ro(self):
        with self.assertRaises(imaging.PhotoError) as cm:
            imaging.prepare(_jpg(200, 150, noise=False))
        self.assertIn("quá nhỏ", str(cm.exception))

    def test_khong_phai_anh(self):
        with self.assertRaises(imaging.PhotoError):
            imaging.prepare(b"khong phai anh")
        with self.assertRaises(imaging.PhotoError):
            imaging.prepare(b"")

    def test_png_trong_suot_doi_sang_jpg(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (600, 800), (10, 20, 30, 0)).save(buf, "PNG")
        out, _ = imaging.prepare(buf.getvalue())
        self.assertEqual(out[:2], b"\xff\xd8")


class TestNaming(unittest.TestCase):
    def test_ma_tren_may_cung_quy_uoc_face_device(self):
        self.assertEqual(naming.device_no("HR-EMP-00070"), "70")
        self.assertEqual(naming.device_no("HR-EMP-00070", "1074"), "1074")

    def test_ten_file_ivms(self):
        self.assertEqual(naming.file_name("70", "Đông Diệp Hữu"), "70_Dong Diep Huu.jpg")
        self.assertEqual(naming.file_name("5", "Linh  Hoang/Nguyen_Thao"), "5_Linh Hoang Nguyen Thao.jpg")


class TestTrang(unittest.TestCase):
    def test_route_dang_ky(self):
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            self.assertIn('{"from_route": "/khuon-mat", "to_route": "khuon_mat"}', fh.read())

    def test_trang_khong_cache_va_escape(self):
        with open(os.path.join(APP, "www", "khuon_mat", "index.py"), encoding="utf-8") as fh:
            self.assertIn("no_cache = 1", fh.read())
        with open(os.path.join(APP, "www", "khuon_mat", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        # moi chuoi du lieu dua vao innerHTML deu qua esc()
        for f in ("r.employee_name", "r.department", "r.device_no", "r.photo_url", "r.uploaded_at"):
            self.assertIn("esc(" + f, html, f)
        self.assertNotIn("window.fetch =", html)



class TestGoiZip(unittest.TestCase):
    """build_zip voi frappe gia: ten anh, csv, chi HR."""

    def _svc(self, roles_ok=True):
        import importlib
        import sys
        import types
        fr = types.ModuleType("frappe")

        class R(dict):
            __getattr__ = dict.get
        emps = [R(name="HR-EMP-00070", employee_name="Đông Diệp Hữu", department="Ops - EC",
                  user_id="dong@x", attendance_device_id=None),
                R(name="HR-EMP-00074", employee_name="Thư Trịnh Minh", department="Finance - EC",
                  user_id="thu@x", attendance_device_id=None)]
        files = [R(name="F1", attached_to_name="HR-EMP-00070", file_url="/private/files/a.jpg",
                   creation="2026-11-05 10:00:00")]

        def get_all(dt, filters=None, fields=None, order_by=None, limit_page_length=None):
            return emps if dt == "Employee" else files
        fr.get_all = get_all
        fr.db = types.SimpleNamespace(sql=lambda *a, **k: [(1,)] if roles_ok else [])
        fr.get_doc = lambda dt, name: types.SimpleNamespace(get_content=lambda: b"JPEGDATA")
        sys.modules["frappe"] = fr
        try:
            from ecentric_workspace.hr.face_photo import service
            return importlib.reload(service)
        finally:
            sys.modules.pop("frappe", None)

    def test_zip_dung_ten_va_danh_sach(self):
        import zipfile
        svc = self._svc()
        data, n, total = svc.build_zip("hr@x")
        self.assertEqual((n, total), (1, 2))
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertIn("anh/70_Dong Diep Huu.jpg", z.namelist())
        self.assertEqual(z.read("anh/70_Dong Diep Huu.jpg"), b"JPEGDATA")
        csv = z.read("danh_sach_nhan_vien.csv").decode("utf-8-sig")
        self.assertIn('70,"Dong Diep Huu","Ops - EC",HR-EMP-00070,x', csv)
        self.assertIn('74,"Thu Trinh Minh","Finance - EC",HR-EMP-00074,', csv)
        self.assertIn("HUONG_DAN.txt", z.namelist())

    def test_chi_hr_tai_duoc(self):
        svc = self._svc(roles_ok=False)
        with self.assertRaises(svc.Forbidden):
            svc.build_zip("nv@x")


if __name__ == "__main__":
    unittest.main()
