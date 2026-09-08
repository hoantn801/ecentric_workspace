# Copyright (c) 2026, eCentric and contributors
"""Nguoi duyet phai mo duoc TEP DINH KEM cua phieu ho co quyen xem (08/09).

Goc van de: `permissions.can_view_request` cho BAT KY ai co dong approver xem toan bo noi dung
phieu, khong phan biet cap. Nhung cong file cua Frappe khong doc luat do - no doc DocShare /
DocPerm. Truoc dot nay DocShare chi duoc cap luc `_activate_level`, nen nguoi duyet cap sau mo
phieu thi thay du gia tri va dieu khoan, bam vao tep thi an 403 tran cua web server. 08/09 CEO
dinh dung ca nay tren EC-CTR-2026-00012.

Bo test giu bon dieu:
  1. Cap cho MOI nguoi duyet trong luong, khong chi cap dang mo.
  2. Khong cap cho Guest / o trong.
  3. Loi khi cap quyen KHONG duoc lam hong viec gui phieu - thieu quyen doc thi nguoi dung van
     mo duoc ho so trong app, chi vuong tep; khong dang danh doi ca lan gui.
  4. Patch cap bu chi dung vao phieu CON MO, va chay lai vo hai.
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
_TRANS = os.path.join(_ROOT, "approval_center", "shared", "workflow", "transitions.py")
_PATCH = os.path.join(_ROOT, "approval_center", "patches", "p163_backfill_approver_file_read.py")


def _func_source(path, name):
    """Boc RIENG mot ham ra khoi module de chay that, khong phai import ca transitions.py
    (no keo theo ca chuc phu thuoc Frappe). Doc bang AST nen khong le thuoc vi tri dong."""
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong thay ham %s trong %s" % (name, path))


class _Rec(object):
    def __init__(self):
        self.granted = []
        self.errors = []


def _run_grant(approvers, grant_raises_for=None):
    rec = _Rec()
    ns = {}
    frappe = types.ModuleType("frappe")
    frappe.get_all = lambda dt, filters=None, pluck=None, **kw: list(approvers)
    frappe.log_error = lambda msg, title=None: rec.errors.append(title)
    frappe.get_traceback = lambda: "TB"
    def _grant(doctype, name, user):
        if grant_raises_for and user in grant_raises_for:
            raise RuntimeError("share loi")
        rec.granted.append((doctype, name, user))
    ns["frappe"] = frappe
    ns["_engine_grant_read"] = _grant
    exec(compile(_func_source(_TRANS, "grant_read_to_snapshot_approvers"),
                 "<grant>", "exec"), ns)
    req = types.SimpleNamespace(name="EC-APR-1", reference_doctype="EC Contract Review Request",
                                reference_name="EC-CTR-2026-00012")
    ns["grant_read_to_snapshot_approvers"](req)
    return rec


class TestGrantOnSubmit(unittest.TestCase):
    def test_cap_cho_moi_nguoi_duyet_khong_chi_cap_dang_mo(self):
        rec = _run_grant(["kieu.nguyen@x", "thu.trinh@x", "lam.nguyen@x"])
        self.assertEqual([u for _d, _n, u in rec.granted],
                         ["kieu.nguyen@x", "thu.trinh@x", "lam.nguyen@x"])
        self.assertTrue(all(d == "EC Contract Review Request" for d, _n, _u in rec.granted))

    def test_bo_qua_guest_va_o_trong(self):
        rec = _run_grant(["a@x", "Guest", None, "", "a@x"])
        self.assertEqual([u for _d, _n, u in rec.granted], ["a@x"])

    def test_loi_cap_quyen_khong_lam_hong_viec_gui(self):
        rec = _run_grant(["a@x", "b@x"], grant_raises_for={"a@x"})
        self.assertEqual([u for _d, _n, u in rec.granted], ["b@x"],
                         "mot nguoi loi thi nhung nguoi con lai van phai duoc cap")
        self.assertTrue(rec.errors, "phai log loi thay vi nem ra ngoai")

    def test_build_snapshot_co_goi_ham_nay(self):
        """Ham dung ma khong ai goi thi vo nghia."""
        src = io.open(_TRANS, encoding="utf-8").read()
        tree = ast.parse(src)
        bs = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "build_snapshot"]
        self.assertTrue(bs)
        called = {n.func.id for n in ast.walk(bs[0])
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("grant_read_to_snapshot_approvers", called)


def _run_patch(reqs, approvers_by_req, existing_shares=()):
    rec = _Rec()
    shares = set(existing_shares)
    frappe = types.ModuleType("frappe")

    def get_all(dt, filters=None, fields=None, pluck=None, **kw):
        if dt == "EC Approval Request":
            return [dict(r) for r in reqs]
        if dt == "EC Approval Request Approver":
            return list(approvers_by_req.get(filters["approval_request"], []))
        return []

    class _DB(object):
        def exists(self, dt, flt):
            return (flt["share_doctype"], flt["share_name"], flt["user"]) in shares

    frappe.get_all = get_all
    frappe.db = _DB()
    frappe.log_error = lambda msg, title=None: rec.errors.append((title, str(msg)[:120]))
    frappe.get_traceback = lambda: "TB"

    transitions = types.ModuleType("transitions")
    def _grant(doctype, name, user):
        rec.granted.append((doctype, name, user)); shares.add((doctype, name, user))
    transitions._engine_grant_read = _grant

    saved = {}
    mods = {"frappe": frappe,
            "ecentric_workspace": types.ModuleType("e"),
            "ecentric_workspace.approval_center": types.ModuleType("a"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("b"),
            "ecentric_workspace.approval_center.shared.workflow": types.ModuleType("c")}
    mods["ecentric_workspace.approval_center.shared.workflow"].transitions = transitions
    mods["ecentric_workspace.approval_center.shared.workflow.transitions"] = transitions
    for k, v in mods.items():
        saved[k] = sys.modules.get(k); sys.modules[k] = v
    try:
        ns = {"__name__": "p163"}
        exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), ns)
        ns["execute"]()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return rec


class TestBackfillPatch(unittest.TestCase):
    _REQ = [{"name": "R1", "reference_doctype": "EC Contract Review Request",
             "reference_name": "EC-CTR-2026-00012"}]

    def test_cap_bu_cho_nguoi_con_thieu(self):
        rec = _run_patch(self._REQ, {"R1": ["a@x", "lam.nguyen@x"]})
        self.assertEqual(sorted(u for _d, _n, u in rec.granted), ["a@x", "lam.nguyen@x"])

    def test_chay_lai_khong_cap_lai(self):
        rec = _run_patch(self._REQ, {"R1": ["a@x"]},
                         existing_shares=[("EC Contract Review Request", "EC-CTR-2026-00012", "a@x")])
        self.assertEqual(rec.granted, [])

    def test_chi_quet_phieu_con_mo(self):
        src = io.open(_PATCH, encoding="utf-8").read()
        self.assertIn('"Pending"', src)
        self.assertIn('"Information Required"', src)
        for closed in ("Approved", "Rejected", "Cancelled"):
            self.assertNotIn('"%s"' % closed, src.split('_OPEN')[1].split("\n")[0],
                             "khong duoc dong den phieu da dong")

    def test_khong_bao_gio_nem_loi(self):
        tree = ast.parse(io.open(_PATCH, encoding="utf-8").read())
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute"]
        self.assertTrue(fn)
        self.assertFalse([n for n in ast.walk(fn[0]) if isinstance(n, ast.Raise)])

    def test_da_dang_ky_trong_patches_txt(self):
        txt = io.open(os.path.join(_ROOT, "patches.txt"), encoding="utf-8").read()
        self.assertIn("patches.p163_backfill_approver_file_read", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
