# Copyright (c) 2026, eCentric and contributors
"""Gửi lại: việc ký phải xảy ra trong CÙNG một thao tác với việc mở lại cấp duyệt.

Báo cáo 29/08 nêu vấn đề số 4: trên đường gửi lại, `_activate_level` chạy vô điều kiện — kể
cả khi gói ký vừa được tạo bản mới và người đề nghị chưa ký lại. Cấp duyệt nhận nhắc việc
trên một gói chưa ký được; bấm "Duyệt & Ký" sẽ lỗi.

Bản sửa ngày 30/08 (`Resubmitter` gọi `sign_on_submit`) đã khép khoảng trống đó mà không cần
đụng vào máy trạng thái của phiếu duyệt:

  * chỉ Payment Request dùng ký số, và nó đi qua `Resubmitter`;
  * ngay sau `engine.resubmit` là chuẩn bị + khoá + ký, trong cùng một request;
  * ký hỏng thì toàn bộ rollback, kể cả nhắc việc vừa tạo.

Nên khoảng "cấp duyệt nhận việc trên gói chưa ký" chỉ còn vài mili giây bên trong một
transaction — không ai thấy được.

Bộ test này KHÔNG sửa gì. Nó chốt lại điều kiện làm cho vấn đề số 4 biến mất, để nếu ai đó
tách việc ký ra khỏi đường gửi lại (chẳng hạn đẩy sang một hàng đợi nền, hoặc để người dùng
tự bấm) thì nó đỏ ngay — chứ không phải phát hiện lại bằng một cấp duyệt bấm nút và gặp lỗi.
"""
import ast
import io
import os
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


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_FIN = _read("approval_center", "shared", "finance_support.py")
_TR = _read("approval_center", "shared", "workflow", "transitions.py")
_DEF = _read("approval_center", "features", "payment_request", "domain", "definition.py")


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong tim thay ham %s" % name)


def _calls_in(src, cls, name):
    """Ten cac ham THUC SU duoc goi trong mot phuong thuc - doc cay cu phap.

    Grep chuoi khong dung duoc o day: chinh chu thich cua `Resubmitter.__call__` co nhac
    `sign_on_submit` de giai thich vi sao no phai nam o day. Ban dau phep kiem dung `assertIn`
    va do la ly do dot bien "bo han buoc ky" VAN XANH. Lan thu tu trong hai ngay dinh dung
    cai bay nay - gio doc cay, khong doc chu.
    """
    node = _method_node(src, cls, name)
    # SAP THEO SO DONG. `ast.walk` duyet theo be rong nen thu tu tra ve KHONG phai thu tu
    # trong ma nguon - phep kiem "ky sau khi mo lai cap" doc nham va bao do tren mot ma
    # nguon hoan toan dung.
    found = [(n.lineno, getattr(n.func, "attr", None) or getattr(n.func, "id", None))
             for n in ast.walk(node) if isinstance(n, ast.Call)]
    return [name_ for _ln, name_ in sorted(found) if name_]


def _method_node(src, cls, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return sub
    raise AssertionError("khong tim thay %s.%s" % (cls, name))


def _method(src, cls, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return ast.get_source_segment(src, sub)
    raise AssertionError("khong tim thay %s.%s" % (cls, name))


class TestSigningHappensInTheSameCall(unittest.TestCase):
    def test_resubmitter_ky_ngay_sau_khi_mo_lai_cap(self):
        calls = _calls_in(_FIN, "Resubmitter", "__call__")
        self.assertIn("resubmit", calls, "phai mo lai cap duyet")
        self.assertIn("sign_on_submit", calls,
                      "mo lai cap ma khong ky = cap duyet nhan viec tren mot goi chua ky duoc")
        self.assertLess(calls.index("resubmit"), calls.index("sign_on_submit"),
                        "phai mo lai cap TRUOC roi ky - nguoc lai thi ky len mot goi chua "
                        "duoc tao ban moi")

    def test_khong_day_viec_ky_sang_hang_doi_nen(self):
        # Day sang nen = ra khoi transaction = cap duyet co the nhan viec that su tren mot
        # goi chua ky duoc, va do chinh la van de so 4 quay lai.
        calls = _calls_in(_FIN, "Resubmitter", "__call__")
        for forbidden in ("enqueue", "enqueue_doc"):
            self.assertNotIn(forbidden, calls,
                             "viec ky phai nam trong cung transaction voi viec mo lai cap")

    def test_ky_hong_thi_khong_nuot(self):
        body = _method(_FIN, "Resubmitter", "__call__")
        tree = ast.parse(body.strip())
        handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
        for h in handlers:
            # `finally` de khoi phuc co mute_messages thi duoc; nuot loi cua sign_on_submit
            # thi khong - mot yeu cau di ra voi goi ky khong dung duoc con te hon mot yeu cau
            # bi tu choi gui.
            src = ast.dump(h)
            self.assertNotIn("sign_on_submit", src,
                             "nuot loi ky = phieu di tiep voi goi ky hong, khong ai biet")


class TestOnlyPaymentRequestUsesSigning(unittest.TestCase):
    """Cac module khac goi thang engine.resubmit - neu mot trong so do bat ky so len thi
    lap luan o tren khong con dung, va bo test nay phai duoc xem lai."""

    def test_chi_mot_ho_so_bat_esign(self):
        import glob
        hits = []
        for p in glob.glob(os.path.join(_ROOT, "approval_center", "features", "*",
                                        "domain", "definition.py")):
            src = io.open(p, encoding="utf-8").read()
            if "esign=True" in src:
                hits.append(os.path.basename(os.path.dirname(os.path.dirname(p))))
        self.assertEqual(hits, ["payment_request"],
                         "co module khac vua bat ky so: %s. Module do goi thang "
                         "engine.resubmit nen KHONG co buoc ky di kem - phai cho no di qua "
                         "Resubmitter truoc da." % hits)


class TestActivationStillHappens(unittest.TestCase):
    """Khong duoc 'sua' van de so 4 bang cach bo luon viec mo lai cap duyet."""

    def test_resubmit_van_mo_lai_cap(self):
        body = _fn(_TR, "resubmit")
        self.assertIn("_activate_level", body,
                      "bo buoc nay thi phieu gui lai xong nam im, khong ai nhan duoc viec")

    def test_mo_dung_cap_dang_do_khong_phai_luon_cap_1(self):
        body = _fn(_TR, "resubmit")
        self.assertIn("resume", body)
        self.assertIn("information_requested_from_level", body,
                      "quay ve cap da yeu cau bo sung, khong bat moi nguoi duyet lai tu dau")


if __name__ == "__main__":
    unittest.main()
