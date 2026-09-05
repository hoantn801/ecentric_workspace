# Copyright (c) 2026, eCentric and contributors
"""Gỡ chứng từ bổ sung tải nhầm — và tuyệt đối không gỡ được thứ đã ký.

Tải nhầm tệp là chuyện bình thường. Không gỡ được thì người đề nghị tải thêm bản đúng và để
cả hai nằm đó; cấp duyệt tự đoán cái nào thật, rồi hồ sơ đi tiếp với một tệp lạ trong danh
sách.

Nhưng đây là hồ sơ duyệt chi tiền, nên cửa phải hẹp. Ba điều kiện, thiếu một là từ chối:

  1. đúng người đề nghị, và phiếu đang ở "Cần bổ sung" — cùng cửa sổ với lúc thêm vào;
  2. tệp KHÔNG thuộc bất kỳ gói ký nào của phiếu, KỂ CẢ gói đã Superseded. Một tệp từng nằm
     trong gói là thứ đã hoặc đang được ký lên; gỡ nó đi là sửa bằng chứng;
  3. gỡ hết cả nhóm tệp trùng nội dung — màn hình gộp chúng thành một dòng, nên gỡ một bản
     ghi mà để lại bản sao thì người dùng thấy tệp "không chịu biến mất".

Và có ghi vết vào lịch sử phiếu: không có thay đổi im lặng nào trên một hồ sơ duyệt chi.
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
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_DS = io.open(os.path.join(_ROOT, "platform", "esign", "document_setup.py"),
              encoding="utf-8").read()
_UI = io.open(os.path.join(_ROOT, "platform", "esign", "ui", "document_signing_section.html"),
              encoding="utf-8").read()


def _fn(name):
    for node in ast.parse(_DS).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(_DS, node)
    raise AssertionError("khong tim thay ham %s" % name)


class _Throw(Exception):
    pass


#: `remove_supporting_attachment` nap engine bang import TRONG than ham, nen ban gia phai
#: con nam trong sys.modules LUC GOI - dat roi go ngay trong _load thi den luc chay that no
#: da bien mat. Cai mot lan cho ca module va TRA LAI o tearDownModule: mot ban gia bo quen
#: trong sys.modules tung lam 5 phep kiem cua bo khac gay (28/08).
_ENGINE_PATH = "ecentric_workspace.approval_center.shared.workflow.transitions"
_SAVED_ENGINE = None
_LOG_SINK = []


def setUpModule():
    global _SAVED_ENGINE
    import sys
    _SAVED_ENGINE = sys.modules.get(_ENGINE_PATH)
    stub = types.ModuleType("transitions")
    stub.log_action = lambda ar, action, actor, **kw: _LOG_SINK.append(
        (action, kw.get("comment")))
    sys.modules[_ENGINE_PATH] = stub


def tearDownModule():
    import sys
    if _SAVED_ENGINE is None:
        sys.modules.pop(_ENGINE_PATH, None)
    else:
        sys.modules[_ENGINE_PATH] = _SAVED_ENGINE


def _load(status="Information Required", is_requester=True, in_package_of=None,
          members=(("F1", "hoa-don.pdf"),), ref="F1"):
    """Chay remove_supporting_attachment THAT.

    `in_package_of` = (business_doctype, business_name) cua goi ky dang giu tep, hoac None.
    """
    deleted = []
    del _LOG_SINK[:]                      # moi lan chay bat dau bang mot so sach

    class _Frappe(object):
        session = types.SimpleNamespace(user="a@x.vn")

        class db(object):
            @staticmethod
            def get_value(dt, filters, field=None, **kw):
                return None

            @staticmethod
            def exists(dt, filters=None):
                # Chi bao "co" khi sha nay nam trong mot goi CUA PHIEU NAY.
                if dt != "EC Digital Signature File":
                    return None
                pkgs = (filters or {}).get("package")
                allowed = pkgs[1] if isinstance(pkgs, (list, tuple)) else []
                return "DSF-1" if allowed else None

        @staticmethod
        def get_all(dt, filters=None, pluck=None, **kw):
            # Cac goi ky CUA CHINH PHIEU NAY. Ban sua 31/08 doi tu "sha nay co o goi nao
            # khong" sang "co o goi nao CUA PHIEU NAY khong" - xem test ben duoi.
            if dt == "EC Digital Signature Package":
                return ["PKG-1"] if (in_package_of and in_package_of[1] == "PR-1") else []
            return []

        @staticmethod
        def delete_doc(dt, name, **kw):
            deleted.append(name)

        @staticmethod
        def throw(msg, exc=None):
            raise _Throw(msg)

        PermissionError = _Throw

    env = {
        "frappe": _Frappe, "_": lambda s: s,
        "perms": types.SimpleNamespace(
            assert_can_view_business=lambda b, n: None,
            business_approval_request=lambda b, n: "AR-1"),
        "_requester_of": lambda b, n: ("a@x.vn" if is_requester else "khac@x.vn"),
        "_can_add_supporting": lambda b, n, mine: bool(mine)
                               and status == "Information Required",
        "_dedupe": lambda files: [{"rep": {"name": members[0][0], "file_name": members[0][1]},
                                   "members": [{"name": m[0]} for m in members]}],
        "_current_files": lambda b, n: [],
        "_rep_sha": lambda rep: "sha-abc",
        "get_document_setup_state": lambda b, n: {"documents": []},
        "DSF": "EC Digital Signature File", "PKG": "EC Digital Signature Package",
    }
    exec(compile(_fn("remove_supporting_attachment"), "document_setup.py", "exec"), env)
    return env["remove_supporting_attachment"], deleted, _LOG_SINK


class TestTheNarrowWindow(unittest.TestCase):
    def test_dang_can_bo_sung_va_dung_nguoi_thi_go_duoc(self):
        fn, deleted, logged = _load()
        out = fn("EC Payment Request", "PR-1", "F1")
        self.assertTrue(out["ok"])
        self.assertEqual(deleted, ["F1"])

    def test_dang_cho_duyet_thi_KHONG(self):
        fn, deleted, _l = _load(status="Pending")
        with self.assertRaises(_Throw):
            fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(deleted, [], "da chan ma van xoa")

    def test_khong_phai_nguoi_de_nghi_thi_KHONG(self):
        fn, deleted, _l = _load(is_requester=False)
        with self.assertRaises(_Throw):
            fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(deleted, [])


class TestNeverRemoveSomethingSigned(unittest.TestCase):
    def test_tep_trong_goi_ky_cua_CHINH_phieu_nay_thi_KHONG(self):
        fn, deleted, _l = _load(in_package_of=("EC Payment Request", "PR-1"))
        with self.assertRaises(_Throw):
            fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(deleted, [], "go tep da ky = sua bang chung")

    def test_tep_trung_noi_dung_voi_goi_cua_PHIEU_KHAC_thi_van_go_duoc(self):
        # Hai phieu co the dinh cung mot to hoa don. Goi ky cua phieu KHAC khong phai ly do
        # de khoa tep tren phieu nay - so sanh phai xet ca chu so huu goi.
        fn, deleted, _l = _load(in_package_of=("EC Payment Request", "PR-KHAC"))
        fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(deleted, ["F1"])


class TestItRemovesTheWholeGroup(unittest.TestCase):
    def test_go_het_ban_trung(self):
        fn, deleted, _l = _load(members=(("F1", "hoa-don.pdf"), ("F2", "hoa-don.pdf"),
                                         ("F3", "hoa-don.pdf")))
        out = fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(sorted(deleted), ["F1", "F2", "F3"],
                         "de lai ban sao = nguoi dung thay tep khong chiu bien mat")
        self.assertEqual(out["removed"], 3)


class TestItLeavesATrace(unittest.TestCase):
    def test_ghi_vao_lich_su_phieu(self):
        fn, _d, logged = _load()
        fn("EC Payment Request", "PR-1", "F1")
        self.assertEqual(len(logged), 1, "khong co thay doi im lang tren ho so duyet chi")
        action, comment = logged[0]
        self.assertEqual(action, "Commented")
        self.assertIn("hoa-don.pdf", comment or "", "phai noi ro go tep nao")


class TestTheButtonIsScopedToTheEditForm(unittest.TestCase):
    """Cai Hoan bao 31/08: mot man hinh co hai cho tai tai lieu."""

    def test_nut_go_chi_ve_cho_bo_chung_tu(self):
        body = _UI.split("function rowHtml")[1][:2400]
        # 05/09: them nhanh "dang lap phieu" (go bat ky tep nao) TRUOC nhanh nay; nhanh
        # "Can bo sung" van chi cho bo chung tu.
        self.assertIn("else if (supporting && STATE && STATE._can_remove_supporting)", body,
                      "chi bo chung tu moi co nut Go o cua so Can bo sung")

    def test_quyen_go_tinh_TRUOC_khi_dung_cac_dong(self):
        # Dat co sau khi da dung dong thi lan ve dau tien khong co nut.
        r = _UI.split("function render()")[1]
        self.assertLess(r.index("_can_remove_supporting = supportOnly"),
                        r.index('getElementById("ecdRows").innerHTML'),
                        "phai tinh quyen truoc khi dung dong")

    def test_chi_thao_tac_duoc_trong_form_sua(self):
        # Kiem CHINH PHEP GAN, khong phai "co chu editingNow o dau do trong ham". Ban dau
        # phep kiem nay chi tim ten bien, nen khi bo `&& editingNow` khoi cong thuc thi bien
        # van con duoc khai bao va test van xanh - mot dot bien lot qua.
        import re
        m = re.search(r"var supportOnly = ([^;]+);", _UI)
        self.assertIsNotNone(m, "khong tim thay cho tinh quyen")
        self.assertIn("editingNow", m.group(1),
                      "quyen tai len/go PHAI phu thuoc vao viec dang o form sua hay khong")
        self.assertIn("_editing()", _UI)
        self.assertIn('classList.contains("payr-editing")', _UI,
                      "doc CO tren <html>, khong soi cau truc DOM cua rieng mot trang")

    def test_ngoai_form_sua_thi_chi_dan_duong(self):
        self.assertIn("Bấm “Chỉnh sửa & gửi lại” để bổ sung chứng từ.", _UI,
                      "nut tat ma khong noi gi = nguoi dung tuong he thong hong")

    def test_goi_endpoint_bang_POST(self):
        body = _UI.split("function removeSupporting")[1][:900]
        self.assertIn('"POST"', body, "endpoint nay GHI - Frappe tu choi ghi qua GET")


class TestBackendDoesNotTrustTheButton(unittest.TestCase):
    def test_backend_kiem_lai_cung_dieu_kien(self):
        body = _fn("remove_supporting_attachment")
        self.assertIn("_can_add_supporting", body,
                      "mot nut khong hien khong phai la mot phep kiem")


if __name__ == "__main__":
    unittest.main()
