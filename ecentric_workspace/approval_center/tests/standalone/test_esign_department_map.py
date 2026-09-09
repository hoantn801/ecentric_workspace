# Copyright (c) 2026, eCentric and contributors
"""Phong ban gui sang SCTS lay theo PHIEU, va buoc doi soat so voi cai DA GUI.

Do that 09/09/2026: phieu cua ban Uyen (phong Service) hien tren cong SCTS thuoc
phong "Data & System", vi `EC Digital Signature Profile.department_id` la mot hang
so ("cntt") gan cho MOI tai lieu.

Ba dieu bo test nay giu:

 1. Co ma phong ban -> gui ma do. Chua co -> LUI VE gia tri Profile, khong nem loi.
    Mot phieu ky khong gui duoc chi vi thieu mot dong cau hinh la cai gia qua dat.
 2. Lui ve thi phai CO TIENG: ghi log de con biet ma dien not. Nhung chi khi phieu
    that su co phong ban - form khong co cot `department` thi im lang moi dung.
 3. **Cai bay that**: buoc doi soat trong service.py so dinh danh do SCTS tra ve voi
    ho so. Truoc day no so voi Profile. Neu gui gia tri dong ma van so voi Profile
    thi moi goi cua phong khac deu bi tu choi ("identity_mismatch:department_id") -
    tuc la sua mot loi hien thi lai lam chet ca luong ky. Test cuoi giu dung cho do.
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


def _load_department_map(*, columns, values, dept_field_value=None):
    """Nap department_map.py voi mot frappe gia. exec(compile(...)) chu khong import:
    __pycache__ tung lam moi dot bien song sot (bai hoc 31/08)."""
    fk = types.ModuleType("frappe")
    fk.logged = []

    class _DB(object):
        def has_column(self, dt, col):
            return col in columns.get(dt, ())

        def get_value(self, dt, name, field):
            return values.get((dt, name, field))

    fk.db = _DB()
    fk.log_error = lambda msg, title=None: fk.logged.append((title, msg))
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fk
    try:
        mod = types.ModuleType("department_map_under_test")
        exec(compile(_read("platform", "esign", "department_map.py"),
                     "department_map.py", "exec"), mod.__dict__)
        return mod, fk
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


_BD = "EC Payment Request"


class TestChonMaPhongBan(unittest.TestCase):
    def test_co_ma_thi_gui_ma_do(self):
        mod, fk = _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): "Service - EC",
                    ("Department", "Service - EC", "custom_scts_department_id"): "service"})
        self.assertEqual(mod.resolve_department_id(_BD, "P1", fallback="cntt"), "service")
        self.assertEqual(fk.logged, [], "duong hanh phuc thi khong ghi log")

    def test_chua_dien_ma_thi_lui_ve_profile_va_KHONG_nem_loi(self):
        mod, fk = _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): "Service - EC",
                    ("Department", "Service - EC", "custom_scts_department_id"): None})
        self.assertEqual(mod.resolve_department_id(_BD, "P1", fallback="cntt"), "cntt")

    def test_lui_ve_thi_phai_co_tieng(self):
        """Im lang = khong ai biet con phong nao chua dien ma."""
        mod, fk = _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): "Service - EC",
                    ("Department", "Service - EC", "custom_scts_department_id"): ""})
        mod.resolve_department_id(_BD, "P1", fallback="cntt")
        self.assertEqual(len(fk.logged), 1)
        self.assertIn("Service - EC", fk.logged[0][1])

    def test_form_khong_co_cot_department_thi_im_lang(self):
        """Nhieu form khong co phong ban - do khong phai viec con thieu, dung ghi log."""
        mod, fk = _load_department_map(columns={}, values={})
        self.assertEqual(mod.resolve_department_id("EC Leave Request", "L1", fallback="cntt"),
                         "cntt")
        self.assertEqual(fk.logged, [])

    def test_phieu_khong_co_phong_ban_cung_im_lang(self):
        mod, fk = _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): None})
        self.assertEqual(mod.resolve_department_id(_BD, "P1", fallback="cntt"), "cntt")
        self.assertEqual(fk.logged, [])

    def test_ma_co_khoang_trang_thua_van_dung_duoc(self):
        mod, _ = _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): "Service - EC",
                    ("Department", "Service - EC", "custom_scts_department_id"): "  service  "})
        self.assertEqual(mod.resolve_department_id(_BD, "P1", fallback="cntt"), "service")

    def test_khong_co_field_tren_Department_thi_van_chay(self):
        """Site chua migrate fixture -> chua co Custom Field. Khong duoc no."""
        mod, _ = _load_department_map(
            columns={_BD: ("department",)},
            values={(_BD, "P1", "department"): "Service - EC"})
        self.assertEqual(mod.resolve_department_id(_BD, "P1", fallback="cntt"), "cntt")

    def test_khong_bao_gio_nem_loi(self):
        mod, _ = _load_department_map(columns={}, values={})
        for args in ((None, None), (_BD, None), (None, "P1")):
            self.assertEqual(mod.resolve_department_id(args[0], args[1], fallback="x"), "x")


class TestGhiMotLan(unittest.TestCase):
    """`create_document` chay lai duoc (thu lai sau loi tam, hoac nhanh doi soat goi
    lai). Neu moi lan chay deu giai lai phong ban thi chi can ai do sua ma giua hai
    lan la gia tri gui lan 2 khac lan 1 - va doi soat sau do so voi mot con so SCTS
    chua bao gio nhan."""

    def _mod(self, dept_code):
        return _load_department_map(
            columns={_BD: ("department",), "Department": ("custom_scts_department_id",)},
            values={(_BD, "P1", "department"): "Service - EC",
                    ("Department", "Service - EC", "custom_scts_department_id"): dept_code})

    def test_lan_dau_giai_va_bao_phai_ghi(self):
        mod, _ = self._mod("service")
        pkg = {"name": "PKG1", "business_doctype": _BD, "business_name": "P1"}
        self.assertEqual(mod.resolve_for_package(pkg, "cntt"), ("service", True))

    def test_lan_sau_GIU_NGUYEN_gia_tri_da_gui(self):
        mod, fk = self._mod("service")
        pkg = {"name": "PKG1", "business_doctype": _BD, "business_name": "P1",
               "department_id_sent": "cntt"}
        self.assertEqual(mod.resolve_for_package(pkg, "cntt"), ("cntt", False),
                         "da gui roi thi khong duoc giai lai")

    def test_doi_ma_phong_ban_giua_chung_KHONG_lam_doi_gia_tri_da_gui(self):
        """Kich ban that: gui lan 1 ra 'cntt', ai do dien ma dung, thu lai lan 2."""
        mod, _ = self._mod("service")
        pkg = {"name": "PKG1", "business_doctype": _BD, "business_name": "P1",
               "department_id_sent": "cntt"}
        code, first = mod.resolve_for_package(pkg, "cntt")
        self.assertEqual(code, "cntt", "lan thu lai phai gui DUNG cai da gui lan dau")
        self.assertFalse(first)

    def test_lan_thu_lai_KHONG_ghi_them_log(self):
        """Ghi mot lan cung la ly do Error Log khong bi dam."""
        mod, fk = self._mod(None)               # chua dien ma -> lan dau se ghi log
        pkg = {"name": "PKG1", "business_doctype": _BD, "business_name": "P1"}
        mod.resolve_for_package(pkg, "cntt")
        self.assertEqual(len(fk.logged), 1)
        pkg["department_id_sent"] = "cntt"      # da ghi lai
        for _ in range(5):
            mod.resolve_for_package(pkg, "cntt")
        self.assertEqual(len(fk.logged), 1, "thu lai nhieu lan van chi mot dong log")

    def test_khong_giai_duoc_thi_khong_bao_ghi(self):
        mod, _ = _load_department_map(columns={}, values={})
        pkg = {"name": "PKG1", "business_doctype": _BD, "business_name": "P1"}
        self.assertEqual(mod.resolve_for_package(pkg, None), (None, False),
                         "khong co gia tri thi dung ghi mot o trong len goi")


class TestGuiVaDoiSoatKhopNhau(unittest.TestCase):
    """Phan de vo nhat: gui gia tri dong nhung doi soat lai so voi hang so."""

    def test_tasks_gui_gia_tri_da_giai_chu_khong_phai_profile(self):
        src = _read("platform", "esign", "tasks.py")
        self.assertIn("department_map.resolve_for_package", src)
        self.assertIn('"department_id": dept_id,', src)
        self.assertNotIn('"department_id": prof.get("department_id"),', src,
                         "payload van dang lay hang so cua Profile")

    def test_tasks_ghi_lai_gia_tri_da_gui_len_goi(self):
        src = _read("platform", "esign", "tasks.py")
        self.assertIn("department_id_sent", src)

    def test_lenh_ghi_len_goi_CO_HANG_RAO(self):
        """Phan quyet dinh (ghi mot lan) da duoc kiem bang hanh vi o resolve_for_package.
        Con LOI GOI trong tasks.py nam trong mot ham 100 dong can frappe, khong chay
        thang duoc - nen chot bang cau truc: lenh ghi phai nam duoi dung co
        `dept_first_time`. Khong co no, mot `if True:` se ghi de len gia tri da gui."""
        src = _read("platform", "esign", "tasks.py")
        found = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.If):
                continue
            body = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
            if "department_id_sent" in body and "set_value" in body:
                found.append(ast.unparse(node.test))
        self.assertEqual(found, ["dept_first_time"],
                         "lenh ghi department_id_sent phai duoc canh boi dung co %s"
                         % "dept_first_time")

    def test_tasks_dung_duong_GHI_MOT_LAN(self):
        """Goi thang resolve_department_id o day = giai lai moi lan thu."""
        src = _read("platform", "esign", "tasks.py")
        self.assertIn("department_map.resolve_for_package", src)
        self.assertNotIn("department_map.resolve_department_id", src)

    def test_package_co_truong_luu_gia_tri_da_gui(self):
        import json
        d = json.loads(_read("approval_center", "doctype", "ec_digital_signature_package",
                             "ec_digital_signature_package.json"))
        f = next((x for x in d["fields"] if x["fieldname"] == "department_id_sent"), None)
        self.assertIsNotNone(f, "goi phai luu duoc ma phong ban da gui")
        self.assertEqual(f.get("read_only"), 1, "gia tri da gui la su that lich su, khong sua tay")

    def _expected_identity(self):
        """Nap RIENG ham expected_identity tu service.py (ca module can frappe).

        Chay ham THAT chu khong doc chuoi: mot phep kiem chi tim thay chu
        "department_id_sent" trong ma nguon van xanh khi ai do boc no vao `if False:` -
        da tu thu dot bien va no SONG SOT, nen phai doi cach do."""
        src = _read("platform", "esign", "service.py")
        tree = ast.parse(src)
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "expected_identity")
        ns = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "service.py", "exec"), ns)
        return ns["expected_identity"]

    def test_doi_soat_so_voi_gia_tri_DA_GUI(self):
        """Neu cho nay quay lai so voi Profile: moi goi cua phong KHAC deu bi tu choi
        doi soat, tuc la mot ban sua nhan lam chet ca luong ky."""
        expected_identity = self._expected_identity()
        prof = {"company_id": "ECENTRIC", "department_id": "cntt"}
        got = expected_identity(prof, {"department_id_sent": "service"})
        self.assertEqual(got["department_id"], "service")
        self.assertEqual(got["company_id"], "ECENTRIC", "cac dinh danh khac giu nguyen")
        self.assertEqual(prof["department_id"], "cntt", "khong duoc sua ho so goc")

    def test_goi_cu_chua_co_gia_tri_da_gui_thi_van_so_voi_Profile(self):
        expected_identity = self._expected_identity()
        prof = {"department_id": "cntt"}
        for pkg in ({}, {"department_id_sent": None}, {"department_id_sent": ""}):
            self.assertEqual(expected_identity(prof, pkg)["department_id"], "cntt")

    def test_nhanh_doi_soat_CO_NAP_cot_department_id_sent(self):
        """Ham dung, loi goi dung, nhung neu truy van khong nap cot do thi `pkg.get()`
        tra None va tat ca lai am tham lui ve Profile. Do la kieu hong khong test nao
        o tren bat duoc - phai chot rieng danh sach cot cua chinh truy van do."""
        src = _read("platform", "esign", "service.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and 'verification_result=\'identity_mismatch:%s\' % key' in ast.unparse(n))
        i = fn.index("EC Digital Signature Package")
        self.assertIn("department_id_sent", fn[i:i + 500],
                      "truy van nap goi phai lay ca cot department_id_sent")

    def test_nhanh_doi_soat_that_su_dung_ham_nay(self):
        """Ham dung ma khong ai goi thi cung bang khong."""
        src = _read("platform", "esign", "service.py")
        # Loc theo LOI GOI events.emit(...) chu khong theo chuoi "identity_mismatch":
        # chuoi do cung nam trong docstring cua chinh expected_identity, nen bo loc cu
        # bat nham vao ham do (test do that, khong phai code sai).
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and 'verification_result=\'identity_mismatch:%s\' % key' in ast.unparse(n))
        self.assertIn("expected_identity(prof, pkg)", fn)
        self.assertIn("expected.get(key)", fn)
        self.assertNotIn("prof.get(key)", fn, "van dang so voi ho so goc")

    def test_field_ship_duoc_qua_fixtures(self):
        """Custom Field khong nam trong fixtures = rebuild site la mat sach, va
        resolver lai am tham lui ve hang so cu."""
        hooks = _read("hooks.py")
        self.assertIn("Department-custom_scts_department_id", hooks)
        fx = _read("fixtures", "custom_field.json")
        self.assertIn("custom_scts_department_id", fx)


if __name__ == "__main__":
    unittest.main()
