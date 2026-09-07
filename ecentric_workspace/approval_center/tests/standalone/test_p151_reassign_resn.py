# Copyright (c) 2026, eCentric and contributors
"""p151 chuyen viec EC-RESN-2026-00002 sang tuan.ly.

Bo test nay giu bon dieu, ca bon deu la dieu de mat neu ai do "don gon" patch:

  1. Phai di qua `transitions.reassign_fulfillment`. Neu ai do doi sang
     `frappe.db.set_value` cho nhanh thi ToDo cua chu cu van mo, chu moi khong nhan
     duoc viec, va so kiem toan khong co dong nao - dung cai bay ma ca engine sinh ra
     de tranh.
  2. Idempotent. `bench migrate` co the chay lai; chay lan hai KHONG duoc goi engine
     them lan nua khi chu da dung.
  3. Khong dung vao ho so da xong. fulfillment_status ngoai (Assigned, In Progress)
     thi bo qua - dung "cuu" mot ho so da hoan tat.
  4. KHONG BAO GIO nem loi. Patch chay trong migrate; mot exception o day lam chet ca
     lan deploy (da dinh voi p116). Ke ca khi engine nem loi, patch phai nuot va log.
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
_PATCH = os.path.join(_ROOT, "approval_center", "patches", "p151_reassign_resn_00002.py")


class _Calls(object):
    def __init__(self):
        self.reassign = []
        self.errors = []


def _load(row, engine_raises=False):
    """Nap patch bang exec(compile(...)) - KHONG spec_from_file_location, vi __pycache__
    lam kiem thu dot bien vo nghia (xem feedback_pycache_defeats_mutation_testing)."""
    calls = _Calls()
    state = {"row": dict(row) if row else None}

    frappe = types.ModuleType("frappe")

    class _DB(object):
        def get_value(self, doctype, name, fields, as_dict=False):
            r = state["row"]
            if r is None:
                return None
            return dict((f, r.get(f)) for f in fields)

    frappe.db = _DB()
    frappe.log_error = lambda msg, title=None: calls.errors.append((title, str(msg)[:200]))
    frappe.get_traceback = lambda: "TRACEBACK"

    def _reassign(doctype, name, new_user, actor=None, description=None):
        calls.reassign.append({"doctype": doctype, "name": name,
                               "new_user": new_user, "actor": actor})
        if engine_raises:
            raise RuntimeError("engine tu choi")
        state["row"]["fulfillment_owner"] = new_user
        state["row"]["fulfillment_status"] = "In Progress"
        return {"owner": new_user}

    transitions = types.ModuleType("transitions")
    transitions.reassign_fulfillment = _reassign

    ns = {"__name__": "p151"}
    saved = {}
    mods = {
        "frappe": frappe,
        "ecentric_workspace": types.ModuleType("ecentric_workspace"),
        "ecentric_workspace.approval_center": types.ModuleType("a"),
        "ecentric_workspace.approval_center.shared": types.ModuleType("b"),
        "ecentric_workspace.approval_center.shared.workflow": types.ModuleType("c"),
        "ecentric_workspace.approval_center.shared.workflow.transitions": transitions,
    }
    mods["ecentric_workspace.approval_center.shared.workflow"].transitions = transitions
    for k, v in mods.items():
        saved[k] = sys.modules.get(k)
        sys.modules[k] = v
    try:
        exec(compile(io.open(_PATCH, encoding="utf-8").read(), _PATCH, "exec"), ns)
        ns["execute"]()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return calls, state


class TestP151(unittest.TestCase):
    def test_di_qua_engine_khong_phai_set_value(self):
        """Soi CAY CU PHAP, khong grep chuoi: chu "set_value" nam trong chu thich
        khong phai loi goi. Grep tho se do khi chu thich nhac den no."""
        tree = ast.parse(io.open(_PATCH, encoding="utf-8").read())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        self.assertIn("reassign_fulfillment", called)
        self.assertNotIn("set_value", called,
                         "patch khong duoc ghi thang; phai qua reassign_fulfillment")

    def test_duong_lanh_chuyen_dung_nguoi_va_dung_actor(self):
        calls, state = _load({"fulfillment_status": "Assigned",
                              "fulfillment_owner": "hoan.tran@ecentric.vn"})
        self.assertEqual(len(calls.reassign), 1)
        c = calls.reassign[0]
        self.assertEqual(c["doctype"], "EC Resignation Request")
        self.assertEqual(c["name"], "EC-RESN-2026-00002")
        self.assertEqual(c["new_user"], "tuan.ly@ecentric.vn")
        self.assertEqual(c["actor"], "hoan.tran@ecentric.vn",
                         "actor phai la chu hien tai, khong phai Administrator")
        self.assertEqual(state["row"]["fulfillment_owner"], "tuan.ly@ecentric.vn")

    def test_chay_lai_khong_goi_engine_lan_hai(self):
        calls, _ = _load({"fulfillment_status": "In Progress",
                          "fulfillment_owner": "tuan.ly@ecentric.vn"})
        self.assertEqual(calls.reassign, [], "da dung chu roi thi phai bo qua")

    def test_ho_so_da_hoan_tat_thi_khong_dung_vao(self):
        calls, _ = _load({"fulfillment_status": "Completed",
                          "fulfillment_owner": "hoan.tran@ecentric.vn"})
        self.assertEqual(calls.reassign, [])

    def test_khong_thay_ho_so_thi_bo_qua(self):
        calls, _ = _load(None)
        self.assertEqual(calls.reassign, [])

    def test_engine_nem_loi_thi_patch_van_khong_lam_chet_migrate(self):
        calls, _ = _load({"fulfillment_status": "Assigned",
                          "fulfillment_owner": "hoan.tran@ecentric.vn"},
                         engine_raises=True)
        self.assertEqual(len(calls.reassign), 1)
        self.assertTrue(any("FAILED" in (t or "") for t, _m in calls.errors),
                        "phai log loi thay vi nem ra ngoai")

    def test_da_dang_ky_trong_patches_txt(self):
        txt = io.open(os.path.join(_ROOT, "patches.txt"), encoding="utf-8").read()
        self.assertIn("patches.p151_reassign_resn_00002", txt,
                      "patch khong nam trong patches.txt thi khong bao gio chay")


if __name__ == "__main__":
    unittest.main(verbosity=2)
