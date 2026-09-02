# Copyright (c) 2026, eCentric and contributors
"""Doi chieu vi tri chu ky phai LAM LAI DUOC, va khong duoc bien thanh duong rut du lieu.

02/09 do tay tren mot tai lieu that: o ky ERP dat 240x120 point, chu ky SCTS dat thuc te
180x90 va lech ~238 point. Bon phep do doc lap deu ra 0.75 = 72/96 - SCTS doc con so minh gui
nhu PIXEL 96 DPI trong khi minh gui POINT. Da bu nghich dao trong `providers/scts.py`, nhung
do la hieu chinh TU DO DAC, chua co xac nhan cua nha cung cap.

Neu SCTS sua phia ho, phep bu se lam lech NGUOC LAI - va khong ai biet, vi chu ky sai vi tri
khong lam hong gi ca, no chi nam sai cho tren chung tu chi tien. Nen viec doi chieu phai chay
lai duoc bat cu luc nao bang mot lenh, khong phai mot lan roi thoi.

`signature_geometry_check` lam viec do. Bo test nay giu ba dieu:

  1. CHI DOC. Khong ky, khong doi trang thai, khong ghi DB. Mot lenh chan doan ma sua duoc du
     lieu la mot lenh nguy hiem hon thu no chan doan.
  2. KHONG RO DU LIEU. Ham nay CO tai ban PDF ve - no bat buoc phai tai de doc o chu ky -
     nhung chi duoc tra ve CON SO. Khong file, khong chu, khong ten nguoi, khong so tien.
  3. Khong hoi duoc nha cung cap thi phai NOI RO VI SAO. Mot khoi rong im lang da tung lam
     mat nua buoi chan doan trong chinh ngay hom nay.
"""
import ast
import io
import os
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
_API = os.path.join(_ROOT, "platform", "esign", "api.py")
_SRC = io.open(_API, encoding="utf-8").read()
_TREE = ast.parse(_SRC)


def _fn(name):
    for n in ast.walk(_TREE):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong tim thay ham %s" % name)


def _calls(node):
    return {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
            for c in ast.walk(node) if isinstance(c, ast.Call)}


class TestChiDoc(unittest.TestCase):
    def test_chi_System_Manager(self):
        self.assertIn("assert_system_manager", _calls(_fn("signature_geometry_check")),
                      "thieu cong quyen -> ai cung tai duoc ban PDF da ky ve")

    def test_la_GET_khong_phai_POST(self):
        fn = _fn("signature_geometry_check")
        for d in fn.decorator_list:
            if isinstance(d, ast.Call):
                for kw in d.keywords:
                    self.assertNotEqual(
                        kw.arg, "methods",
                        "khai methods=[POST] bien mot lenh chi-doc thanh mot lenh ghi")

    def test_khong_goi_bat_ky_ham_GHI_nao(self):
        goi = _calls(_fn("signature_geometry_check"))
        for cam in ("approve_and_sign", "transition_with_recipients", "set_dsr_status",
                    "set_value", "save", "insert", "delete_doc", "emit", "log_action"):
            self.assertNotIn(cam, goi,
                             "lenh chan doan goi %s -> no khong con la chi-doc" % cam)


class TestKhongRoDuLieu(unittest.TestCase):
    """Ham CO tai PDF ve - bat buoc phai the de doc o chu ky - nhung chi duoc tra CON SO."""

    def test_khong_tra_noi_dung_file(self):
        than = ast.get_source_segment(_SRC, _fn("signature_geometry_check")) or ""
        for cam in ('"content"', "'content'", "b64", "base64", "PdfBase64"):
            self.assertNotIn(cam, than.replace('res["content"]', ""),
                             "tra %s ra ngoai = bien lenh chan doan thanh duong rut file"
                             % cam)

    def test_ham_doc_hinh_hoc_chi_tra_con_so(self):
        than = ast.get_source_segment(_SRC, _fn("_pdf_signature_geometry")) or ""
        self.assertIn("page_size", than)
        self.assertIn("signature_rects", than)
        for cam in ("extract_text", "get_contents", "/T", "email", "name"):
            self.assertNotIn(cam, than,
                             "doc %s tu PDF la doc NOI DUNG, khong phai hinh hoc" % cam)

    def test_chi_doc_annotation_chu_ky(self):
        than = ast.get_source_segment(_SRC, _fn("_pdf_signature_geometry")) or ""
        self.assertIn("/Sig", than,
                      "phai loc dung annotation chu ky, khong quet bua moi annotation")


class TestKhongHoiDuocThiNoiRoViSao(unittest.TestCase):
    def test_MOI_nhanh_except_deu_ghi_lai_ly_do(self):
        """Kiem CAU TRUC, khong grep chu.

        Ban dau phep kiem nay chi tim chuoi `safe_error` trong than ham. Mot phep dot bien
        lam rong MOT nhanh except van xanh, vi nhanh con lai giu nguyen chuoi do - test do
        cho mot ham da bi bit mat mot mat. Nen no duyet TUNG `except`.

        Lan hai (02/09): no lai qua chat theo huong nguoc lai - doi dung mot dia chi
        `row["error"]`, nen khi them mot nhanh bat loi o CAP GOI (ghi ly do vao
        `signed_check`) thi test do do, du nhanh do co ghi ly do day du. Phep kiem phai bam
        vao Y DINH "moi nhanh deu ghi lai ly do da lam sach", khong bam vao CHINH TA cua bien
        nhan ly do.
        """
        fn = _fn("signature_geometry_check")
        handlers = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)]
        self.assertTrue(handlers, "ham khong bat loi nha cung cap -> mot loi mang lam do ca "
                                  "lenh chan doan")
        for h in handlers:
            ghi = [a.value for a in ast.walk(h) if isinstance(a, ast.Assign)]
            self.assertTrue(ghi, "co nhanh except khong gan gi ca - loi bi nuot tron")
            for v in ghi:
                self.assertFalse(
                    isinstance(v, ast.Constant) and not v.value,
                    "nhanh except gan hang rong/None = nuot loi co ve lich su hon nhung van "
                    "la nuot")
            self.assertIn("safe_error",
                          {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                           for n in ghi for c in ast.walk(n) if isinstance(c, ast.Call)},
                          "phai dung safe_error - ghi thang exception co the lo bi mat")

    def test_moi_tep_deu_mang_bo_ba_asked_ok_error(self):
        than = ast.get_source_segment(_SRC, _fn("signature_geometry_check")) or ""
        for k in ('"asked"', '"ok"', '"error"'):
            self.assertIn(k, than,
                          "thieu %s thi khong phan biet duoc 'hoi duoc ma rong' voi "
                          "'khong hoi duoc'" % k)


class TestSoSanhDungConSo(unittest.TestCase):
    """`y_top` KHONG phai con so gui di - phai lat truc doc truoc khi so voi PDF."""

    def test_placements_tra_ve_lly_da_lat(self):
        than = ast.get_source_segment(_SRC, _fn("signature_geometry_check")) or ""
        self.assertIn("lly_sent", than,
                      "so `y_top` voi `/Rect` cua PDF la so hai he toa do khac nhau - luon "
                      "lech 842 - y - h va nguoi doc se tuong bu sai")
        self.assertIn("_page_height_or", than,
                      "phai lat theo chieu cao trang THAT doc tu PDF, khong doan 842")


class TestChuaKyXongPhaiNoiDungLyDo(unittest.TestCase):
    """Bao sai ly do con hai hon khong bao gi - no dieu nguoi doc di duong khac.

    02/09 lenh nay tra ve `SCTS refused get_pdf (HTTP 400)` tren mot tai lieu moi ky 2/5 chan.
    Toi doc thanh loi cua nha cung cap, truy sang `scts_document_file_id` dang trong, va suyt
    ket luan do la nguyen nhan goc - trong khi truong do von duoc backfill cho san. Su that chi
    la: chua ky xong thi lam gi co ban da ky ma tai.
    """

    def _fn_src(self):
        return ast.get_source_segment(_SRC, _fn("signature_geometry_check")) or ""

    def test_hoi_da_ky_xong_chua_TRUOC_khi_tai(self):
        """Cong phai chan TRUOC, khong phai doan lai tu thong bao loi cua nha cung cap."""
        fn = _fn("signature_geometry_check")
        vong = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
        self.assertTrue(vong, "khong con vong lap qua tung tep")
        for v in vong:
            tai = [i for i, st in enumerate(v.body)
                   if "get_signed_document" in (ast.get_source_segment(_SRC, st) or "")]
            if not tai:
                continue
            # Cong phai xet DUNG BIEN. Phien ban dau chi doi "co mot `if` nao do chua
            # `continue`", nen dot bien `if not da_ky:` -> `if False:` van xanh: cong con do
            # nhung khong bao gio dong. Mot cong luon mo trong khong khac gi mot cong that.
            chan = [i for i, st in enumerate(v.body)
                    if isinstance(st, ast.If)
                    and any(isinstance(c, ast.Continue) for c in ast.walk(st))
                    and "da_ky" in {getattr(n, "id", None) for n in ast.walk(st.test)}
                    # ...va dung CHIEU. `if da_ky: continue` cung nhac `da_ky`, cung co
                    # `continue`, nhung bo qua dung luc DA ky xong - tuc dao nguoc y nghia
                    # ma van qua moi phep kiem cu.
                    and isinstance(st.test, ast.UnaryOp)
                    and isinstance(st.test.op, ast.Not)]
            self.assertTrue(chan, "khong co cong xet `da_ky` roi bo qua -> van goi get_pdf "
                                  "roi bao 'nha cung cap tu choi'")
            self.assertLess(min(chan), min(tai),
                            "cong dat SAU lenh tai = vo nghia, PDF da duoc doi ve roi")

    def test_dung_CHUNG_cong_voi_duong_tai_that(self):
        """Phai GOI, khong phai chi `import`.

        Phien ban dau chi tim chuoi `_terminal_signed_ok` trong than ham, nen dot bien thay
        loi goi bang hang `(True, "x")` van xanh: dong `import` con nguyen nen chuoi van con.
        Dung dung mot lop nham lan da phai sua ba lan hom nay - grep chu thay vi doc cau truc.
        """
        self.assertIn("_terminal_signed_ok", _calls(_fn("signature_geometry_check")),
                      "phai GOI cong cua signed_files - hai dinh nghia 'da ky xong' lech nhau "
                      "thi chan doan noi mot dang, san xuat lam mot dang")

    def test_khong_tu_dinh_nghia_lai_the_nao_la_ky_xong(self):
        than = self._fn_src()
        for cam in ("_TERMINAL_SIGNED", '"completed"', '"finished"', '"success"'):
            self.assertNotIn(cam, than,
                             "chep lai danh sach trang thai terminal (%s) = tao ban sao thu "
                             "hai se troi khoi ban goc" % cam)

    def test_noi_ro_la_KHONG_hoi_chu_khong_phai_hoi_roi_rong(self):
        than = self._fn_src()
        self.assertIn('row["asked"] = False', than,
                      "de asked=True tren nhanh khong-hoi = nguoi doc tuong day la cau tra loi "
                      "cua nha cung cap; day dung la lop nham lan da lam mat buoi chieu 02/09")


if __name__ == "__main__":
    unittest.main()
