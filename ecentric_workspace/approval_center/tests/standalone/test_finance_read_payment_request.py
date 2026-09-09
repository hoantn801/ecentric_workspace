# Copyright (c) 2026, eCentric and contributors
"""Nguoi XU LY phai mo duoc tep dinh kem cua phieu ho co quyen xem (09/09, Hoan chot).

Cung goc van de voi test_approver_file_read, doi chan. `d914f2d1` mo danh sach cho Fulfiller
duoc cau hinh; nhung cong file cua Frappe doc DocShare/DocPerm chu khong doc
`can_view_request`. Do tren production 09/09: chi Dan thay 32 phieu chi, 32/32 co tep, 122 tep
rieng tu, ma chi duoc DocShare tren dung 1 ho so -> bam vao tep la 403.

Hoan chot cap theo ROLE chu khong theo tung nguoi: Fulfiller cua De nghi thanh toan von da la
Role `EC Finance` (p149), nen cap quyen doc cho chinh role do thi them/bo nguoi trong role la
quyen doi theo ngay, khong con buoc thu cong nao.

Bo test giu bon dieu:
  1. Cap DUNG Role `EC Finance` tren DUNG `EC Payment Request`.
  2. CHI cap `read`. Them `write`/`export`/`report`/... vao GRANTS thi test do - vi day la
     bang chua so tien va chi tiet ngan hang cua toan cong ty.
  3. Thieu Role hoac thieu DocType thi bo qua trong im lang, KHONG nem - patch chay trong
     migrate, mot exception giet ca lan deploy (p116).
  4. Phai xoa cache DocType, neu khong quyen vua cap khong co hieu luc ngay.
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
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_PATCH = os.path.join(_ROOT, "approval_center", "patches",
                      "p170_ec_finance_role_read_payment_request.py")
_PATCHES_TXT = os.path.join(_ROOT, "patches.txt")

# Quyen KHONG duoc phep cap o patch nay - la mot phan cua hop dong, khong phai goi y.
_CAM = ("write", "create", "delete", "submit", "cancel", "amend", "export", "report", "share")


class _Rec(object):
    def __init__(self):
        self.added = []
        self.props = []
        self.cleared = []
        self.errors = []


def _load_patch(exists=None, add_raises=False):
    """Nap module patch that bang exec(compile(...)) - KHONG import, de __pycache__ khong
    vo hieu hoa kiem thu dot bien."""
    rec = _Rec()
    exists = {"Role": True, "DocType": True} if exists is None else exists

    frappe = types.ModuleType("frappe")
    frappe.db = types.SimpleNamespace(exists=lambda dt, name: bool(exists.get(dt, False)))
    frappe.clear_cache = lambda doctype=None: rec.cleared.append(doctype)
    frappe.log_error = lambda msg, title=None: rec.errors.append(title)
    frappe.get_traceback = lambda: "TB"

    perms = types.ModuleType("frappe.permissions")

    def _add(doctype, role, permlevel):
        if add_raises:
            raise RuntimeError("add_permission no")
        rec.added.append((doctype, role, permlevel))

    perms.add_permission = _add
    perms.update_permission_property = (
        lambda dt, role, lvl, ptype, value, validate=True:
        rec.props.append((dt, role, lvl, ptype, value)))
    frappe.permissions = perms

    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.permissions")}
    sys.modules["frappe"] = frappe
    sys.modules["frappe.permissions"] = perms
    try:
        ns = {"__name__": "p169_under_test"}
        exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), ns)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return ns, rec


class TestCapQuyen(unittest.TestCase):
    def test_cap_dung_role_va_dung_doctype(self):
        ns, rec = _load_patch()
        ns["execute"]()
        self.assertEqual(rec.added, [("EC Payment Request", "EC Finance", 0)])

    def test_chi_cap_read(self):
        ns, rec = _load_patch()
        ns["execute"]()
        self.assertEqual([p[3] for p in rec.props], ["read"])
        self.assertTrue(all(p[4] == 1 for p in rec.props))

    def test_khong_bao_gio_cap_quyen_ghi_hay_ket_xuat(self):
        """Hop dong: bang nay chua so tien va chi tiet ngan hang."""
        ns, _rec = _load_patch()
        grants = set(ns["GRANTS"])
        self.assertEqual(grants, {"read"})
        for cam in _CAM:
            self.assertNotIn(cam, grants, "khong duoc cap '%s' o patch nay" % cam)

    def test_xoa_cache_doctype(self):
        """Khong xoa cache thi quyen vua cap chua co hieu luc."""
        ns, rec = _load_patch()
        ns["execute"]()
        self.assertIn("EC Payment Request", rec.cleared)


class TestKhongGietMigrate(unittest.TestCase):
    def test_thieu_role_thi_bo_qua_khong_nem(self):
        ns, rec = _load_patch(exists={"Role": False, "DocType": True})
        ns["execute"]()
        self.assertEqual(rec.added, [], "khong duoc cap khi role chua ton tai")
        self.assertEqual(rec.props, [])
        self.assertTrue(rec.errors, "phai ghi log de admin biet ma tao role")

    def test_thieu_doctype_thi_bo_qua_khong_nem(self):
        ns, rec = _load_patch(exists={"Role": True, "DocType": False})
        ns["execute"]()
        self.assertEqual(rec.added, [])
        self.assertTrue(rec.errors)

    def test_loi_khi_cap_khong_nem_ra_ngoai(self):
        """Mot exception trong patch giet ca lan migrate (bai hoc p116)."""
        ns, rec = _load_patch(add_raises=True)
        try:
            ns["execute"]()
        except Exception as exc:  # pragma: no cover - chinh la thu dang chan
            self.fail("execute() nem ra ngoai: %r" % (exc,))
        self.assertTrue(rec.errors, "nuot loi thi it nhat phai ghi log")


class TestDangKyPatch(unittest.TestCase):
    def test_co_dong_trong_patches_txt_va_o_CUOI_file(self):
        lines = [l.strip() for l in io.open(_PATCHES_TXT, encoding="utf-8").read().splitlines()
                 if l.strip()]
        dong = "ecentric_workspace.approval_center.patches.p170_ec_finance_role_read_payment_request"
        self.assertIn(dong, lines, "patch khong chay neu khong khai bao trong patches.txt")
        self.assertEqual(lines[-1], dong,
                         "QUY_TAC_TRANH_CONFLICT: dong moi chi duoc NOI O CUOI file")


if __name__ == "__main__":
    unittest.main(verbosity=2)
