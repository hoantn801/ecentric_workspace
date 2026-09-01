# Copyright (c) 2026, eCentric and contributors
"""Phong ban tren Payment Request khong doi duoc sau khi gui duyet.

`department` lai HAI thu cung luc:
  * EC Viewer Permission - ai duoc nhin thay phieu;
  * dinh tuyen cap duyet L1 - truong bo phan nao la nguoi duyet.

Ma `save_draft` van chay duoc khi phieu o trang thai "Information Required" (bi tra lai) va
ghi moi truong trong `editable_fields`; `department` lai KHONG nam trong `MATERIAL_FIELDS`
nen doi no cung khong lam duyet lai tu dau. Ghep lai: mot phieu bi tra lai co the doi phong
ban roi gui lai, va no di tiep tren chuoi duyet da chot cho phong ban CU - nguoi le ra khong
duoc xem thi nhin thay, nguoi le ra phai duyet thi khong.

Ra soat 01/09: 8/27 form da khoa tu truoc, Payment Request thi chua - trong khi no la form
chi tien. Hoan chot chi lam cho Payment Request.
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
        if os.path.isdir(os.path.join(root, "approval_center", "doctype")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_PATH = os.path.join(_ROOT, "approval_center", "doctype", "ec_payment_request",
                     "ec_payment_request.py")
_SRC = io.open(_PATH, encoding="utf-8").read()


class _Thrown(Exception):
    pass


def _load_controller():
    """Nap controller THAT voi frappe gia - chay ham, khong grep chu."""
    fake = types.ModuleType("frappe")
    fake._ = lambda s: s

    def throw(msg, exc=None):
        raise _Thrown(msg)

    fake.throw = throw
    model = types.ModuleType("frappe.model")
    doc = types.ModuleType("frappe.model.document")

    class Document(object):
        pass

    doc.Document = Document
    model.document = doc
    fake.model = model

    import sys
    saved = {k: sys.modules.get(k) for k in
             ("frappe", "frappe.model", "frappe.model.document")}
    sys.modules["frappe"] = fake
    sys.modules["frappe.model"] = model
    sys.modules["frappe.model.document"] = doc
    env = {}
    try:
        exec(compile(_SRC, "ec_payment_request.py", "exec"), env)
        return env["ECPaymentRequest"]
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class _Before(object):
    def __init__(self, dept):
        self.department = dept


def _doc(cls, dept, before_dept, is_new=False, approval_request="AR-1"):
    d = cls()
    d.department = dept
    d.approval_request = approval_request
    d.is_new = lambda: is_new
    d.get_doc_before_save = lambda: (_Before(before_dept) if before_dept is not None else None)
    return d


class TestDepartmentIsFrozenAfterSubmit(unittest.TestCase):
    def setUp(self):
        self.cls = _load_controller()

    def test_doi_phong_ban_sau_khi_gui_bi_chan(self):
        d = _doc(self.cls, "Finance - EC", "Operation - EC")
        with self.assertRaises(_Thrown) as ctx:
            d.validate()
        self.assertIn("Phòng ban", str(ctx.exception))

    def test_giu_nguyen_phong_ban_thi_qua(self):
        d = _doc(self.cls, "Operation - EC", "Operation - EC")
        d.validate()          # khong duoc nem

    def test_ban_nhap_van_doi_thoai_mai(self):
        """Chua gui (khong co approval_request) thi khong khoa gi."""
        d = _doc(self.cls, "Finance - EC", "Operation - EC", approval_request=None)
        d.validate()

    def test_phieu_moi_khong_bi_chan(self):
        d = _doc(self.cls, "Finance - EC", "Operation - EC", is_new=True)
        d.validate()

    def test_phong_ban_cu_TRONG_thi_cho_dien_vao(self):
        """Du lieu cu thieu phong ban thi phai cho bo sung, khong khoa oan."""
        d = _doc(self.cls, "Finance - EC", "")
        d.validate()


class TestTheLockIsWiredIntoValidate(unittest.TestCase):
    """Ham co ton tai ma khong ai goi thi vo dung - da tung gap dung kieu do."""

    def test_validate_goi_ham_khoa(self):
        tree = ast.parse(_SRC)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "validate":
                fn = node
        self.assertIsNotNone(fn, "controller khong con ham validate()")
        called = {getattr(c.func, "attr", None) for c in ast.walk(fn)
                  if isinstance(c, ast.Call)}
        self.assertIn("_department_snapshot_lock", called,
                      "validate() phai goi _department_snapshot_lock - dinh nghia ma khong "
                      "goi thi khoa khong bao gio chay")


if __name__ == "__main__":
    unittest.main()
