# Copyright (c) 2026, eCentric and contributors
"""Tai tep KHONG duoc di qua phep kiem DocPerm chuan - nhan vien thuong se bi 403.

03/09: chi Hien (Employee, Customer, PM Member) bam "+ Tai tai lieu" trong khoi ky so va
thay "1 tep loi". Tai hien bang chinh phien cua chi:

    POST /api/method/upload_file (kem doctype + docname) -> 403
    "User hien.nguyen does not have doctype access via role permission"

`upload_file` la endpoint CUA FRAPPE, kiem quyen bang DocPerm CHUAN tren DocType. Do bang du
lieu tren production: ca 8 DocType yeu cau chi co MOT dong DocPerm cho System Manager, khong
dong nao cho Employee/All - vi kien truc nay co y cho moi duong ghi di qua app method co
guard. Nen gui kem doctype/docname la tu chuoc mot phep kiem quyen ma he thong khong dung.

Hau qua: khong nhan vien nao thiet lap duoc tai lieu ky so. Hoan khong thay vi System Manager
duoc bo qua moi kiem tra - va cho toi hom do chi co Hoan thu. Day la ly do "mot phieu that,
nguoi that" la dieu kien de dong, chu khong phai "chay duoc tren may minh".

13 form khac da lam dung tu lau (tai len khong kem doctype/docname roi gan bang app method).
Bo test nay giu ba dieu:
  1. Khoi ky so khong con gui doctype/docname.
  2. Endpoint gan tep TU KIEM QUYEN, va dung LAI cong da co - khong dinh nghia cong thu hai.
  3. Khong keo duoc tep cua ho so KHAC ve phieu minh bang mot `file_url` tuy y.
"""
import ast
import io
import os
import re
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


def _read(*rel):
    return io.open(os.path.join(_ROOT, *rel), encoding="utf-8").read()


def _code_only(s):
    """Bo chu thich JS va Python. Chu thich cua chinh ban sua NHAC toi doctype/docname de
    giai thich vi sao KHONG dung - grep tho se bat oan dung cau van dang canh bao."""
    s = re.sub(r"/\*[\s\S]*?\*/", "", s)
    s = re.sub(r"(?m)^\s*//.*$", "", s)
    s = re.sub(r'"""[\s\S]*?"""', "", s)
    return re.sub(r"(?m)^\s*#.*$", "", s)


_SIGNING_UI = "platform/esign/ui/document_signing_section.html"


class TestKhoiKySoKhongGuiDoctype(unittest.TestCase):
    def setUp(self):
        self.src = _code_only(_read(*_SIGNING_UI.split("/")))

    def test_khong_gui_doctype_docname_kem_upload_file(self):
        i = self.src.find("/api/method/upload_file")
        self.assertNotEqual(i, -1, "khoi ky so khong con tai tep - test nay da mu")
        truoc = self.src[max(0, i - 900):i]
        for cam in ('fd.append("doctype"', "fd.append('doctype'",
                    'fd.append("docname"', "fd.append('docname'"):
            self.assertNotIn(cam, truoc,
                             "gui %s kem upload_file = Frappe kiem DocPerm chuan = 403 voi "
                             "moi nhan vien thuong" % cam)

    def test_co_goi_app_method_de_gan_tep(self):
        """Tai len khong kem doctype thi tep MO COI - phai co buoc gan, khong thi nguoi dung
        tai xong ma ho so khong thay tep nao."""
        self.assertIn("attach_uploaded_file", self.src,
                      "tai len xong ma khong gan vao phieu = tep bien mat")
        i = self.src.find("attach_uploaded_file")
        self.assertIn('"POST"', self.src[i:i + 200],
                      "lenh GHI ma goi kieu GET thi Frappe tu choi")


class TestEndpointTuKiemQuyen(unittest.TestCase):
    def setUp(self):
        self.src = _read("platform", "esign", "document_setup.py")
        self.tree = ast.parse(self.src)
        self.fn = next((n for n in ast.walk(self.tree)
                        if isinstance(n, ast.FunctionDef) and n.name == "attach_uploaded_file"),
                       None)
        self.assertIsNotNone(self.fn, "khong con ham gan tep")

    def _calls(self):
        return {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                for c in ast.walk(self.fn) if isinstance(c, ast.Call)}

    def test_kiem_quyen_xem_ho_so(self):
        self.assertIn("assert_can_view_business", self._calls())

    def test_dung_LAI_hai_cong_da_co(self):
        """Khong dinh nghia cong thu ba. Hai cong lech nhau = mot cua so mo ra ma khong ai
        biet - dung lop loi da phai sua o `_terminal_signed_ok` va `may_have_sent`."""
        goi = self._calls()
        self.assertIn("_can_add_supporting", goi, "thieu cua so 'dang bi tra lai'")
        self.assertIn("_assert_setup_editable", goi, "thieu cua so 'dang lap ho so'")
        self.assertIn("_assert_can_classify", goi, "thieu phep kiem dung nguoi de nghi")

    def test_khong_keo_duoc_tep_cua_ho_so_khac(self):
        than = ast.get_source_segment(self.src, self.fn) or ""
        self.assertIn("attached_to_name", than,
                      "khong xet tep da thuoc ho so nao chua -> mot file_url tuy y keo duoc "
                      "tep cua phieu nguoi khac ve phieu minh")
        i = than.find("if existing.attached_to_name:")
        self.assertNotEqual(i, -1)
        self.assertIn("PermissionError", than[i:i + 600],
                      "tep thuoc ho so khac phai bi TU CHOI, khong phai lam ngo")

    def test_chi_nhan_duong_dan_tep_hop_le(self):
        than = ast.get_source_segment(self.src, self.fn) or ""
        self.assertIn('startswith(("/files/", "/private/files/"))', than,
                      "khong chan duong dan la thi nhan duoc chuoi bat ky")


class TestEndpointWhitelistDungKieu(unittest.TestCase):
    def test_la_POST_va_qua_business_args(self):
        src = _read("platform", "esign", "api.py")
        tree = ast.parse(src)
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "attach_uploaded_file"), None)
        self.assertIsNotNone(fn, "chua co endpoint whitelisted")
        decos = [ast.get_source_segment(src, d) or "" for d in fn.decorator_list]
        self.assertTrue(any('methods=["POST"]' in d for d in decos), "lenh GHI phai la POST")
        goi = {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
               for c in ast.walk(fn) if isinstance(c, ast.Call)}
        self.assertIn("_business_args", goi)


class TestKhongTaiPham(unittest.TestCase):
    """Chan lop loi nay quay lai o CAC TRANG KHAC.

    Nam cho con lai (system_request, document_request, data_request, resignation, MSO cu) van
    gui doctype/docname - biet, va cach ly co ten o day. Danh sach chi duoc NGAN di, khong
    duoc dai them: them mot cai moi la test do.
    """
    #: Moi dong PHAI kem ly do. Mot danh sach cach ly khong ghi ly do se thanh vinh vien.
    #: Phep kiem nay tim ra 6 cho ma grep tay cua toi bo sot (regex hep hon) - nen con so
    #: that la 11, khong phai 5.
    CACH_LY = {
        # O "tep hoan tat / ket qua" cua NGUOI XU LY, khong phai nguoi de nghi. Nguoi xu ly
        # cac form nay hien chi la Hoan (System Manager) va Dong (EC Ops System) - hai nguoi
        # duy nhat co quyen - nen chua ai gap. Van hong voi bat ky nguoi xu ly nao khac.
        "approval_center/features/system_request/ui/main_section.html",
        "approval_center/features/document_request/ui/main_section.html",
        "approval_center/features/data_request/ui/main_section.html",
        "approval_center/features/resignation/ui/main_section.html",
        "approval_center/features/ai_topup/ui/main_section.html",
        "approval_center/features/asset_request/ui/main_section.html",
        # Trang cu (MSO/SO/PO/GBS): `doctype` la BIEN chay theo loai chung tu, va cac DocType
        # do co bo quyen rieng - phai do tung cai truoc khi sua, khong sua mu.
        "legacy_pages/mso_plan_form/main_section.html",
        "legacy_pages/approval_page/main_section.html",
        "legacy_pages/gbs_po_form_v2/main_section.html",
        "legacy_pages/gbs_so_form_v2/main_section.html",
    }

    def test_danh_sach_cach_ly_khong_dai_them(self):
        vi_pham = set()
        for dirpath, _dirs, files in os.walk(_ROOT):
            for fn in files:
                if not fn.endswith(".html"):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, _ROOT).replace("\\", "/")
                body = _code_only(io.open(p, encoding="utf-8").read())
                if "/api/method/upload_file" not in body:
                    continue
                if re.search(r"""append\(\s*['"]doctype['"]""", body):
                    vi_pham.add(rel)
        self.assertTrue(vi_pham <= self.CACH_LY,
                        "trang MOI gui doctype/docname kem upload_file -> nhan vien thuong se "
                        "bi 403: %s" % sorted(vi_pham - self.CACH_LY))

    def test_cach_ly_khong_rong_tron(self):
        """Khi sua het 5 cho, danh sach ve rong va phep kiem tren thanh vo nghia - luc do
        phai xoa ca lop test nay MOT CACH CO Y, khong de no am tham gac mot tap rong."""
        con = {p for p in self.CACH_LY if os.path.exists(os.path.join(_ROOT, *p.split("/")))}
        self.assertTrue(con, "moi trang cach ly da bien mat - xoa lop test nay di")


if __name__ == "__main__":
    unittest.main()
