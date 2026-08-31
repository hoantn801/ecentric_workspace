# Copyright (c) 2026, eCentric and contributors
"""Phiếu bị từ chối: tạo lại được, và tạo lại KHÔNG được ký thay người dùng.

Phiếu bị từ chối là ngõ cụt vĩnh viễn — đúng thiết kế: `resubmit` chỉ nhận trạng thái
"Information Required", và hộp thoại từ chối nói thẳng với cấp duyệt là "sau khi từ chối,
yêu cầu sẽ kết thúc". Phần đó giữ nguyên.

Cái không ổn là phần sau đó: người đề nghị phải gõ lại từ đầu và tải lại từng tệp, kể cả khi
bị từ chối chỉ vì sai một con số.

Và đường này vừa thành đường chính chứ không còn là ngoại lệ: đã chốt 30/08 rằng muốn đổi
TÀI LIỆU CẦN KÝ thì cấp duyệt Từ chối, vì SCTS chỉ nhận danh sách tệp lúc tạo tài liệu.

Ba điều bộ test này giữ:
  1. chỉ tạo lại được từ trạng thái ĐÃ KẾT THÚC, và chỉ người đề nghị;
  2. ô cam kết cá nhân KHÔNG được chép — chép là ký thay họ;
  3. tệp chép hỏng phải BÁO RA, không nuốt như đường đính kèm cũ vẫn làm.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "shared")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _src(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_CS = _src("approval_center", "shared", "requests", "command_service.py")
_DEF = _src("approval_center", "features", "payment_request", "domain", "definition.py")
_UI = _src("approval_center", "features", "payment_request", "ui", "main_section.html")


def _fn_src(name):
    """Ma nguon cua DUNG mot ham, boc bang AST.

    Cat bang chuoi thi keo theo ca ham dung sau no - loi dau tien cua chinh bo test nay.
    """
    tree = ast.parse(_CS)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(_CS, node)
    raise AssertionError("khong tim thay ham %s" % name)


class _Throw(Exception):
    pass


class _Doc(dict):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.doctype = kw.get("doctype", "EC Payment Request")
        self.name = kw.get("name")
        self.inserted = False

    def get(self, k, default=None):
        return dict.get(self, k, default)

    def set(self, k, v):
        self[k] = v

    def __getattr__(self, k):
        # Document cua Frappe tra None cho truong chua gan, khong nem AttributeError.
        return self.get(k)

    def __setattr__(self, k, v):
        # `doc.requested_by = user` phai NHIN THAY duoc qua `doc.get("requested_by")`.
        # Ban dau stub chi ghi vao __dict__ nen phep kiem doc ra None va bao do - loi cua
        # ban gia, khong phai cua ma nguon. Mot ban gia lech voi that thi test do o cho no
        # nen xanh va xanh o cho no nen do.
        self[k] = v

    def insert(self, **kw):
        self.inserted = True
        self.name = self.name or "PR-NEW"
        return self


def _load(source_fields, status, actor="a@x.vn", requested_by="a@x.vn",
          files=None, fail_urls=()):
    """Chay clone_request THAT voi frappe gia."""
    src = ("_CLONEABLE = (\"Rejected\", \"Cancelled\")\n"
           "_SYSTEM_FILE_PREFIXES = (\"SIGNED-\", \"REVIEW-\")\n"
           + _fn_src("clone_request") + "\n" + _fn_src("_is_system_artefact")
           + "\n" + _fn_src("_copy_attachments"))

    inserted_files = []
    created = []                      # phieu MOI - de test soi vao ket qua, khong doan

    class _Frappe(object):
        session = types.SimpleNamespace(user=actor)

        @staticmethod
        def get_doc(arg, name=None):
            if isinstance(arg, dict):                 # insert File
                if arg.get("file_url") in fail_urls:
                    class _Boom(object):
                        def insert(self, **kw):
                            raise Exception("khong gan duoc")
                    return _Boom()
                inserted_files.append(arg)
                return _Doc(**arg)
            return _Doc(doctype=arg, name=name, requested_by=requested_by, **source_fields)

        @staticmethod
        def new_doc(doctype):
            d = _Doc(doctype=doctype)
            created.append(d)
            return d

        @staticmethod
        def get_all(dt, filters=None, fields=None, **kw):
            return list(files or [])

        @staticmethod
        def throw(msg, exc=None):
            raise _Throw(msg)

        PermissionError = _Throw

    caps = types.SimpleNamespace(
        approval_request_for=lambda d, n: (types.SimpleNamespace(approval_status=status)
                                           if status else None),
        is_system_manager=lambda u: False,
        derive=lambda u, b, r: {})
    qs = types.SimpleNamespace(
        employee_context=lambda u: {"employee": "EMP-1", "department": "IT", "company": "EC"})

    env = {"frappe": _Frappe, "_": lambda s: s, "capabilities": caps, "query_service": qs}
    exec(compile(src, "command_service.py", "exec"), env)
    return env["clone_request"], inserted_files, created


def _definition(exclude=("details_and_attachments_correct",)):
    return types.SimpleNamespace(
        business_doctype="EC Payment Request",
        editable_fields=("payment_amount", "reason", "details_and_attachments_correct",
                         "request_attachment"),
        clone_exclude_fields=exclude,
        draft_preparer=None, title_builder=lambda d: "tieu de",
        status_label_map={"Pending": "Đang phê duyệt"})


class TestOnlyFromAFinishedRequest(unittest.TestCase):
    def test_bi_tu_choi_thi_tao_lai_duoc(self):
        fn, _f, _new = _load({"payment_amount": 10}, "Rejected")
        out = fn(_definition(), "PR-1")
        self.assertEqual(out["name"], "PR-NEW")

    def test_da_huy_thi_tao_lai_duoc(self):
        fn, _f, _new = _load({"payment_amount": 10}, "Cancelled")
        self.assertEqual(fn(_definition(), "PR-1")["name"], "PR-NEW")

    def test_dang_cho_duyet_thi_KHONG(self):
        fn, _f, _new = _load({"payment_amount": 10}, "Pending")
        with self.assertRaises(_Throw):
            fn(_definition(), "PR-1")

    def test_da_duyet_thi_KHONG(self):
        fn, _f, _new = _load({"payment_amount": 10}, "Approved")
        with self.assertRaises(_Throw):
            fn(_definition(), "PR-1")

    def test_dang_can_bo_sung_thi_KHONG(self):
        # Trang thai nay da co duong rieng - "Chinh sua & gui lai". Mo them ban sao o day
        # se de ra hai ho so cung song cho cung mot khoan chi.
        fn, _f, _new = _load({"payment_amount": 10}, "Information Required")
        with self.assertRaises(_Throw):
            fn(_definition(), "PR-1")

    def test_nguoi_khac_thi_KHONG(self):
        fn, _f, _new = _load({"payment_amount": 10}, "Rejected",
                       actor="b@x.vn", requested_by="a@x.vn")
        with self.assertRaises(_Throw):
            fn(_definition(), "PR-1")


class TestItDoesNotSignOnTheirBehalf(unittest.TestCase):
    def test_o_cam_ket_KHONG_duoc_chep(self):
        fn, _f, _new = _load({"payment_amount": 10, "reason": "abc",
                        "details_and_attachments_correct": "Yes"}, "Rejected")
        fn(_definition(), "PR-1")
        doc = _new[0]
        # Soi vao PHIEU MOI, khong phai vao danh sach cau hinh: cau hinh dung ma vong lap
        # chep bo qua thi test van phai do.
        self.assertIsNone(doc.get("details_and_attachments_correct"),
                          "chep o cam ket sang phieu moi = tich thay nguoi dung cho mot bo "
                          "ho so ho chua doc lai")

    def test_payment_request_thuc_su_khai_bao_loai_tru(self):
        self.assertIn("clone_exclude_fields", _DEF)
        self.assertIn("details_and_attachments_correct", _DEF.split("clone_exclude_fields")[1])

    def test_cac_truong_khac_van_duoc_chep(self):
        fn, _f, _new = _load({"payment_amount": 10, "reason": "abc"}, "Rejected")
        fn(_definition(), "PR-1")
        doc = _new[0]
        self.assertEqual(doc.get("payment_amount"), 10)
        self.assertEqual(doc.get("reason"), "abc")
        self.assertEqual(doc.get("requested_by"), "a@x.vn")
        # KHONG duoc mang theo lien ket sang ho so duyet cu.
        self.assertIsNone(doc.get("approval_request"))
        self.assertIsNone(doc.get("submitted_at"))


class TestAttachmentFailuresAreReported(unittest.TestCase):
    def test_chep_du_tep(self):
        files = [{"file_url": "/private/a.pdf", "file_name": "a.pdf", "is_private": 1},
                 {"file_url": "/private/b.pdf", "file_name": "b.pdf", "is_private": 1}]
        fn, ins, _new = _load({"payment_amount": 10}, "Rejected", files=files)
        out = fn(_definition(), "PR-1")
        self.assertEqual(out["attachments_copied"], 2)
        self.assertEqual(out["attachments_failed"], [])
        self.assertEqual(len(ins), 2)

    def test_tep_trung_url_chi_chep_mot_lan(self):
        files = [{"file_url": "/private/a.pdf", "file_name": "a.pdf", "is_private": 1},
                 {"file_url": "/private/a.pdf", "file_name": "a.pdf", "is_private": 1}]
        fn, _i, _new = _load({"payment_amount": 10}, "Rejected", files=files)
        self.assertEqual(fn(_definition(), "PR-1")["attachments_copied"], 1)

    def test_tep_hong_duoc_BAO_RA_chu_khong_nuot(self):
        files = [{"file_url": "/private/a.pdf", "file_name": "a.pdf", "is_private": 1},
                 {"file_url": "/private/hong.pdf", "file_name": "hong.pdf", "is_private": 1}]
        fn, _i, _new = _load({"payment_amount": 10}, "Rejected", files=files,
                       fail_urls=("/private/hong.pdf",))
        out = fn(_definition(), "PR-1")
        self.assertEqual(out["attachments_copied"], 1)
        self.assertEqual(out["attachments_failed"], ["hong.pdf"],
                         "nuot loi o day = nguoi dung tuong ho so day du trong khi thieu tep")


class TestSystemArtefactsAreNotCopied(unittest.TestCase):
    """PDF DA KY cua phieu cu khong duoc di theo sang phieu moi.

    `requester._add_requester_pdf_files` nap MOI PDF private dinh kem vao goi ky voi
    requires_signature=1. Chep mot ban da ky sang phieu moi nghia la phieu moi doi nguoi ta
    dat o ky len mot tai lieu da co chu ky so cua phieu truoc.
    """

    def _files(self):
        return [{"file_url": "/private/to-trinh.pdf", "file_name": "to-trinh.pdf",
                 "is_private": 1},
                {"file_url": "/private/SIGNED-to-trinh.pdf",
                 "file_name": "SIGNED-to-trinh.pdf", "is_private": 1},
                {"file_url": "/private/REVIEW-abc12345-to-trinh.pdf",
                 "file_name": "REVIEW-abc12345-to-trinh.pdf", "is_private": 1}]

    def test_chi_chep_tep_nguoi_dung_dinh_kem(self):
        fn, ins, _new = _load({"payment_amount": 10}, "Rejected", files=self._files())
        out = fn(_definition(), "PR-1")
        names = sorted(f["file_name"] for f in ins)
        self.assertEqual(names, ["to-trinh.pdf"],
                         "PDF da ky / ban doi chieu la tep HE THONG sinh ra, khong phai ho so")
        self.assertEqual(out["attachments_copied"], 1)

    def test_khong_bao_loi_cho_tep_bi_bo_qua(self):
        # Bo qua co chu dich khac han voi chep hong - khong duoc bao vao danh sach loi.
        fn, _i, _new = _load({"payment_amount": 10}, "Rejected", files=self._files())
        self.assertEqual(fn(_definition(), "PR-1")["attachments_failed"], [])


class TestTheOldRequestIsUntouched(unittest.TestCase):
    def test_khong_ghi_gi_len_phieu_cu(self):
        tree = ast.parse(_fn_src("clone_request"))
        writes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") in ("set_value", "delete_doc", "save")]
        self.assertEqual(writes, [], "ban sao khong duoc dung vao phieu cu")


class TestTheButtonAppearsOnlyThere(unittest.TestCase):
    def test_nut_chi_hien_khi_da_tu_choi_hoac_da_huy(self):
        line = [l for l in _UI.split("\n") if 'data-act="clone"' in l and "btns.push" in l]
        self.assertTrue(line, "khong tim thay nut tao phieu moi")
        ctx = _UI.split('data-act="clone"')[0].split("\n")[-3:]
        joined = "\n".join(ctx)
        self.assertIn("Rejected", joined)
        self.assertIn("Cancelled", joined)

    def test_chi_nguoi_de_nghi_thay_nut(self):
        ctx = _UI.split('data-act="clone"')[0].split("\n")[-3:]
        self.assertIn("isMine(det)", "\n".join(ctx),
                      "cap duyet xem duoc phieu nay - tao lai la viec cua nguoi de nghi")

    def test_hoi_truoc_khi_tao(self):
        self.assertIn("Tạo phiếu mới từ phiếu này", _UI)
        body = _UI.split("function doClone")[1][:900]
        self.assertIn("modal(", body, "phai hoi truoc: no dieu huong sang phieu khac")
        self.assertIn("giữ nguyên", body, "phai noi ro phieu cu khong bi dung toi")


if __name__ == "__main__":
    unittest.main()
