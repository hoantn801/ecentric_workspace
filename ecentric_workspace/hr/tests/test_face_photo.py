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


def _ai(**kw):
    d = {"faces": 1, "top": 550, "left": 400, "bottom": 900, "right": 600, "face_cut_off": False,
         "frontal": True, "eyes_open": True, "mask": False, "sunglasses": False, "covered": False,
         "blurry": False, "too_dark": False, "photo_of_screen": False, "heavy_filter": False}
    d.update(kw)
    return d


class TestAiCheck(unittest.TestCase):
    """v2: AI soi anh - chan anh hong, cat cho mat vao giua, AI loi van nhan."""

    def test_anh_dat(self):
        from ecentric_workspace.hr.face_photo import ai_check
        problems, box = ai_check.decide(_ai())
        self.assertEqual(problems, [])
        self.assertEqual(box, (0.55, 0.4, 0.9, 0.6))

    def test_cac_loi_chan(self):
        from ecentric_workspace.hr.face_photo import ai_check as A
        self.assertEqual(A.decide(_ai(faces=0))[0], [A.MSG["no_face"]])
        self.assertIn(A.MSG["many"], A.decide(_ai(faces=2))[0])
        self.assertIn(A.MSG["face_cut_off"], A.decide(_ai(face_cut_off=True))[0])
        self.assertIn(A.MSG["frontal"], A.decide(_ai(frontal=False))[0])
        self.assertIn(A.MSG["sunglasses"], A.decide(_ai(sunglasses=True))[0])
        # model tra CHUOI: "false" khong duoc thanh True
        self.assertEqual(A.decide(_ai(mask="false", frontal="true"))[0], [])
        self.assertIn(A.MSG["mask"], A.decide(_ai(mask="true"))[0])

    def test_khung_vo_ly_thi_khong_cat(self):
        from ecentric_workspace.hr.face_photo import ai_check
        self.assertIsNone(ai_check.box_of(_ai(top=500, bottom=505)))
        self.assertIsNone(ai_check.box_of(_ai(top=0, left=0, bottom=1000, right=1000)))
        self.assertIsNone(ai_check.box_of(_ai(top="abc")))

    def test_cat_mat_vao_giua_anh_the(self):
        from ecentric_workspace.hr.face_photo import ai_check
        # anh 1280x960 (may tinh), mat lech xuong duoi (giong anh Hoan gui 05/11)
        x0, y0, x1, y1 = ai_check.crop_rect((0.55, 0.4, 0.9, 0.6), 1280, 960, 240)
        self.assertTrue(0 <= x0 < x1 <= 1280 and 0 <= y0 < y1 <= 960)
        self.assertAlmostEqual((x1 - x0) / float(y1 - y0), 0.8, places=2)
        fy0, fy1, fx0, fx1 = 0.55 * 960, 0.9 * 960, 0.4 * 1280, 0.6 * 1280
        self.assertTrue(y0 <= fy0 and fy1 <= y1 and x0 <= fx0 and fx1 <= x1)   # ca mat nam trong
        self.assertGreaterEqual(min(x1 - x0, y1 - y0), 240)

    def test_ask_loi_tra_none(self):
        from ecentric_workspace.hr.face_photo import ai_check

        def boom(*a, **k):
            raise RuntimeError("x")
        self.assertIsNone(ai_check.ask(b"j", boom))
        self.assertIsNone(ai_check.ask(b"j", lambda *a, **k: {"ok": False, "error": "no_key"}))
        got = ai_check.ask(b"j", lambda *a, **k: {"ok": True, "data": _ai()})
        self.assertEqual(got["faces"], 1)

    def test_service_chan_cat_va_ai_loi(self):
        from PIL import Image
        svc = TestGoiZip._svc(TestGoiZip())
        img = Image.new("RGB", (1280, 960), (120, 120, 120))
        ok = lambda *a, **k: {"ok": True, "data": _ai()}
        out, check, _, problems = svc.check_photo(img, generate=ok)
        self.assertEqual((check, problems), ("ok", []))
        self.assertAlmostEqual(out.size[0] / float(out.size[1]), 0.8, places=2)
        bad = lambda *a, **k: {"ok": True, "data": _ai(face_cut_off=True)}
        _, check, _, problems = svc.check_photo(img, generate=bad)
        self.assertEqual(check, "review")
        self.assertTrue(problems)
        down = lambda *a, **k: {"ok": False, "error": "ai_disabled"}
        out, check, _, problems = svc.check_photo(img, generate=down)
        self.assertEqual((check, problems, out.size), ("unchecked", [], (1280, 960)))
        self.assertEqual(svc.check_of("ec_face_HR-EMP-00070__ai.jpg"), "ok")
        self.assertEqual(svc.check_of("ec_face_HR-EMP-00070__hrxem.jpg"), "review")
        self.assertEqual(svc.check_of("ec_face_HR-EMP-00070.jpg"), "unchecked")


if __name__ == "__main__":
    unittest.main()
