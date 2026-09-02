# Copyright (c) 2026, eCentric and contributors
"""SCTS phan biet DOCUMENT id voi WORKFLOW INSTANCE id. Toan he dang gui nham cai dau.

Do bang tay 02/09 tren tai lieu f3a2c0f7-...: goi `/api/Workflow/{id}` bang document id tra
404 voi CA BA nguoi - ke ca Lien la nguoi da ky that tren chinh tai lieu do. Khong phai
chuyen quyen, la sai ma.

Chuoi hau qua, va la ly do bo test nay ton tai:

  document id gui vao Workflow -> 404
    -> `discover_transition` khong bao gio chay duoc
    -> khong biet transitionId dung cua canh hien tai
    -> gui id cau hinh cu -> SCTS 400 "Duong chuyen khong hop le"
    -> roi ve pool -> `bulk-process` nhan `instanceIds` cung bang document id
    -> 2xx kem bulkJobTransactionId, roi KHONG KY GI CA

Duong `transition` con bao 400 ngay. Duong pool im lang - do la hinh dang that bai da lam
mat nhieu buoi nhat trong ca vu nay. Neu ai do sau nay "don dep" bang cach cho lai `doc_id`
vao mot trong hai cho, no se im lang y het nhu cu.
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


def _src(rel):
    return io.open(os.path.join(_ROOT, "platform", "esign", rel), encoding="utf-8").read()


def _fn(src, name):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong tim thay ham %s" % name)


def _call_args(node, fname):
    """Ten cac doi so vi tri cua MOI loi goi `fname` trong `node`."""
    out = []
    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        if (getattr(c.func, "attr", None) or getattr(c.func, "id", None)) != fname:
            continue
        args = []
        for a in c.args:
            if isinstance(a, ast.Name):
                args.append(a.id)
            elif isinstance(a, ast.List) and len(a.elts) == 1 and isinstance(a.elts[0], ast.Name):
                args.append("[%s]" % a.elts[0].id)      # approve_and_sign([x], ...)
            else:
                args.append("?")
        out.append(args)
    return out


class TestKhongGuiDocumentIdVaoWorkflow(unittest.TestCase):
    """Ba cho nhan INSTANCE id. Ca ba deu tung nhan document id."""

    def setUp(self):
        self.tasks = _src("tasks.py")

    def _kiem(self, fname, vi_tri=0):
        goi = _call_args(_fn(self.tasks, "_send_one"), fname) if self._co_send_one() \
            else _call_args(ast.parse(self.tasks), fname)
        self.assertTrue(goi, "khong con loi goi %s nao - test nay da mu" % fname)
        for args in goi:
            self.assertGreater(len(args), vi_tri, "%s goi thieu doi so" % fname)
            self.assertNotIn(args[vi_tri], ("doc_id", "[doc_id]"),
                             "%s dang nhan document id o vi tri %d -> SCTS 404/im lang"
                             % (fname, vi_tri))

    def _co_send_one(self):
        try:
            _fn(self.tasks, "_send_one")
            return True
        except AssertionError:
            return False

    def test_transition_with_recipients_nhan_instance_id(self):
        self._kiem("transition_with_recipients")

    def test_approve_and_sign_nhan_instance_id(self):
        """Duong pool. Cho nay nguy hiem nhat vi no tra 2xx roi khong lam gi."""
        self._kiem("approve_and_sign")

    def test_plan_handover_nhan_instance_id(self):
        for c in ast.walk(ast.parse(self.tasks)):
            if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "plan_handover":
                for kw in c.keywords:
                    if kw.arg == "instance_id":
                        self.assertNotEqual(
                            getattr(kw.value, "id", None), "doc_id",
                            "plan_handover nhan document id -> kham pha canh chuyen 404")
                        return
        self.fail("khong tim thay loi goi plan_handover(instance_id=...)")

    def test_poll_status_VAN_dung_document_id(self):
        """Doi xung: `/api/Document/{id}` that su nhan DOCUMENT id.

        Doi het sang instance id la sua qua tay - va se hong mot duong dang chay tot.
        """
        goi = _call_args(ast.parse(self.tasks), "poll_status") \
            + _call_args(ast.parse(_src("api.py")), "poll_status")
        self.assertTrue(goi, "khong con loi goi poll_status nao - test nay da mu")
        self.assertTrue(any(a and a[0] in ("doc_id", "document_id", "pkg") for a in goi),
                        "poll_status khong con nhan document id - da doi nham ca cho dung")


class TestOTraveKhongDuocImLang(unittest.TestCase):
    def test_khong_co_ma_thi_noi_ro_la_co_the_sai(self):
        src = _src("api.py")
        than = ast.get_source_segment(src, _fn(src, "provider_workflow_view")) or ""
        self.assertIn("instance_id_source", than,
                      "khong noi ma dang dung tu dau thi nguoi doc khong biet ket qua 404 la "
                      "do ma sai hay do nguoi sai - dung cau hoi da ton ca buoi 02/09")
        self.assertIn("CO THE SAI", than,
                      "khi phai lui ve document id thi PHAI danh dau - im lang o day chinh la "
                      "cach loi nay song sot lau den vay")

    def test_helper_cho_phep_tu_choi_lui_ve_document_id(self):
        than = ast.get_source_segment(_src("package.py"),
                                      _fn(_src("package.py"), "workflow_instance_id")) or ""
        self.assertIn("fallback_to_document", than,
                      "nguoi goi phai tu chon co dam dung document id khong; lui ve mac dinh "
                      "va im lang la dung cai bay vua mat mot ngay de tim ra")


class TestDatMaLaViecCoGhiVet(unittest.TestCase):
    def setUp(self):
        self.src = _src("api.py")
        self.fn = _fn(self.src, "set_workflow_instance_id")

    def _goi(self):
        return {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                for c in ast.walk(self.fn) if isinstance(c, ast.Call)}

    def test_chi_System_Manager(self):
        self.assertIn("assert_system_manager", self._goi(),
                      "ai cung doi duoc ma workflow = ai cung chuyen huong duoc lenh ky")

    def test_la_POST(self):
        for d in self.fn.decorator_list:
            if isinstance(d, ast.Call):
                methods = [kw for kw in d.keywords if kw.arg == "methods"]
                self.assertTrue(methods, "lenh GHI ma khai bao nhu GET")
                return
        self.fail("thieu decorator whitelist")

    def test_ghi_lai_truoc_va_sau(self):
        """Kiem trong CHINH loi goi emit, khong grep ca than ham.

        Ban dau test nay tim chuoi `"truoc"` o bat cu dau trong ham - va cau `return` cung co
        chuoi do, nen go han `"truoc"` ra khoi emit van xanh: vet kiem toan mat sach trong khi
        gia tri tra ve cho nguoi goi thi con. Dung lop nham lan da phai sua ba lan hom nay.
        """
        emits = [c for c in ast.walk(self.fn)
                 if isinstance(c, ast.Call)
                 and (getattr(c.func, "attr", None) or getattr(c.func, "id", None)) == "emit"]
        self.assertTrue(emits, "doi ma ma khong de lai vet = mot thay doi khong truy duoc")
        noi_dung = " ".join(ast.get_source_segment(self.src, c) or "" for c in emits)
        for k in ('"truoc"', '"sau"'):
            self.assertIn(k, noi_dung,
                          "emit thieu %s - neu ma moi sai thi khong co duong quay lai" % k)

    def test_khong_doan_ma_tu_document_id(self):
        than = ast.get_source_segment(self.src, self.fn) or ""
        self.assertNotIn("scts_document_id", than,
                         "suy ma instance tu ma document la dung lai chinh gia dinh da sai")


if __name__ == "__main__":
    unittest.main()
