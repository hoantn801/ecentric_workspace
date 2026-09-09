# Copyright (c) 2026, eCentric and contributors
"""Lop ky so phai hoi LUAT GOC ve "ai duoc xem", khong giu ban sao rieng (09/09).

Trieu chung: chi Dan (Ke toan, Fulfiller cua PAYMENT_REQUEST) mo EC-PAYR-2026-00073 - than
phieu ve binh thuong nhung moi endpoint ky so nem "Ban khong co quyen xem yeu cau nay", bung
bon cap thong bao chong len trang. `esign.permissions.can_view_business` chep lai ba chan
(nguoi tao / SM / nguoi duyet) tu mot quy uoc DA DOI tu lau.

Bo test giu bon dieu:
  1. Nguoi XU LY duoc xem (day la thu vua sua).
  2. Ba chan cu KHONG mat: nguoi tao, SM, nguoi duyet.
  3. Nguoi ngoai van bi chan - noi rong khong duoc bien thanh mo toang.
  4. `upload_package_file` (GHI) van dung luat CU. Day la diem de sai nhat: no gac bang dung
     mot cau, neu dung chung voi luat xem da noi rong thi nguoi xu ly lang le duoc quyen ghi.
"""
import ast
import io
import os
import sys
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
_PERMS = os.path.join(_ROOT, "platform", "esign", "permissions.py")
_API = os.path.join(_ROOT, "platform", "esign", "api.py")

_BD, _BN, _AR = "EC Payment Request", "EC-PAYR-2026-00073", "EC-APR-73"


def _load(fn, user, requested_by="ai.do@x", approvers=(), roles=(), fulfillment_owner=None,
          canon=None, canon_raises=False):
    """Nap permissions.py that bang exec(compile(...)) voi mot frappe gia."""
    frappe = types.ModuleType("frappe")
    frappe.session = types.SimpleNamespace(user=user)
    frappe._ = lambda s: s
    frappe.PermissionError = type("PermissionError", (Exception,), {})
    frappe.log_error = lambda *a, **k: None
    frappe.get_traceback = lambda: "TB"
    frappe.get_roles = lambda u=None: list(roles)

    def _get_value(dt, name, field, as_dict=False):
        if dt == _BD and as_dict:
            return {"requested_by": requested_by, "fulfillment_owner": fulfillment_owner,
                    "approval_type": "PAYMENT_REQUEST"}
        if dt == _BD and field == "requested_by":
            return requested_by
        if dt == _BD and field == "approval_request":
            return _AR
        return None

    def _exists(dt, filters):
        if dt == "EC Approval Request Approver":
            return filters.get("approver") in approvers
        return False

    frappe.db = types.SimpleNamespace(
        has_column=lambda dt, col: True, get_value=_get_value, exists=_exists)

    def _throw(msg, exc=None):
        raise (exc or Exception)(msg)
    frappe.throw = _throw

    # luat goc gia
    wf = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
    def _canon(*a, **k):
        if canon_raises:
            raise RuntimeError("khong nap duoc")
        return bool(canon)
    wf.can_view_request = _canon

    saved = dict(sys.modules)
    sys.modules["frappe"] = frappe
    mod = "ecentric_workspace.approval_center.shared.workflow.permissions"
    if canon_raises:
        sys.modules.pop(mod, None)
        class _Blocker(object):
            def find_module(self, name, path=None):
                return self if name == mod else None
            def load_module(self, name):
                raise ImportError("chan co y")
        sys.meta_path.insert(0, _Blocker())
    else:
        sys.modules[mod] = wf
    try:
        ns = {"__name__": "esign_perms_under_test"}
        exec(compile(io.open(_PERMS, encoding="utf-8").read(), _PERMS, "exec"), ns)
        # PHAI goi NGAY TRONG khoi da va module gia: lenh `from ... import can_view_request`
        # nam BEN TRONG ham, nen no chay luc GOI chu khong phai luc nap. Ban dau bo test nay
        # tra sys.modules ve truoc khi goi -> ca bon ca "nguoi xu ly" deu do vi mot ly do
        # thuoc ve phep do, khong phai thuoc ve code.
        return ns[fn](_BD, _BN)
    finally:
        if canon_raises:
            sys.meta_path.pop(0)
        sys.modules.clear()
        sys.modules.update(saved)


def _view(**kw):
    return _load(fn="can_view_business", **kw)


def _setup(**kw):
    return _load(fn="can_setup_package", **kw)


class TestNguoiXuLyDuocXem(unittest.TestCase):
    def test_nguoi_xu_ly_duoc_xem(self):
        """Thu vua sua: luat goc noi duoc thi lop ky so phai theo."""
        self.assertTrue(_view(user="dan.ha@x", canon=True))

    def test_luat_goc_noi_khong_thi_van_chan(self):
        self.assertFalse(_view(user="nguoi.la@x", canon=False))


class TestBaChanCuKhongMat(unittest.TestCase):
    def test_nguoi_tao(self):
        self.assertTrue(_view(user="ai.do@x", requested_by="ai.do@x", canon=False))

    def test_system_manager(self):
        self.assertTrue(_view(user="sm@x", roles=("System Manager",), canon=False))

    def test_nguoi_duyet(self):
        self.assertTrue(_view(user="duyet@x", approvers=("duyet@x",), canon=False))


class TestFailClosed(unittest.TestCase):
    def test_khong_nap_duoc_luat_goc_thi_lui_ve_luat_cu_chu_khong_mo_toang(self):
        self.assertFalse(_view(user="dan.ha@x", canon_raises=True),
                         "nhap loi phai tra False, khong duoc coi nhu duoc phep")
        self.assertTrue(_view(user="ai.do@x", requested_by="ai.do@x", canon_raises=True),
                        "nguoi tao van phai xem duoc du khong nap duoc luat goc")


class TestGhiVanDungLuatCu(unittest.TestCase):
    def test_nguoi_xu_ly_KHONG_duoc_sua_goi_tai_lieu(self):
        self.assertFalse(_setup(user="dan.ha@x", canon=True),
                         "noi rong quyen XEM khong duoc keo theo quyen GHI")

    def test_nguoi_tao_va_nguoi_duyet_van_sua_duoc(self):
        self.assertTrue(_setup(user="ai.do@x", requested_by="ai.do@x", canon=False))
        self.assertTrue(_setup(user="duyet@x", approvers=("duyet@x",), canon=False))

    def test_upload_package_file_goi_dung_cong_GHI(self):
        """Doc THAN ham trong api.py: phai goi assert_can_setup_package, khong phai
        assert_can_view_business."""
        src = io.open(_API, encoding="utf-8").read()
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "upload_package_file"]
        self.assertTrue(fn, "khong tim thay upload_package_file")
        goi = {n.func.attr for n in ast.walk(fn[0])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("assert_can_setup_package", goi)
        self.assertNotIn("assert_can_view_business", goi,
                         "endpoint GHI khong duoc gac bang cau hoi QUYEN XEM")


if __name__ == "__main__":
    unittest.main(verbosity=2)
