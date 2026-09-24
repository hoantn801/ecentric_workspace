# Copyright (c) 2026, eCentric and contributors
"""p206: chuyen EC-AITOP-2026-00029 ve dong.diep phai di DUNG duong engine.

set_value tay se de lai ToDo mo cua chu cu va nguoi moi khong co viec trong hop - dung loi p151
da tranh. Chay patch bang frappe gia de kiem ca ba nhanh: chuyen that, da xong thi bo qua,
va loi engine thi nuot (patch nem loi la chet ca lan migrate)."""
import io
import os
import types
import unittest

_P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "patches",
                  "p206_reassign_aitop_00029.py")


def _chay(snap, loi_engine=False):
    ghi = {"reassign": [], "set_value": [], "log": []}
    fr = types.SimpleNamespace(
        db=types.SimpleNamespace(get_value=lambda *a, **k: snap,
                                 set_value=lambda *a, **k: ghi["set_value"].append(a)),
        log_error=lambda *a, **k: ghi["log"].append(a), get_traceback=lambda: "tb")

    def reassign(dt, name, new, actor=None):
        if loi_engine:
            raise RuntimeError("khong du dieu kien")
        ghi["reassign"].append((dt, name, new, actor))
    src = io.open(_P, encoding="utf-8").read().replace(
        "import frappe\n", "").replace(
        "from ecentric_workspace.approval_center.shared.workflow import transitions\n", "")
    ns = {"frappe": fr, "transitions": types.SimpleNamespace(reassign_fulfillment=reassign)}
    exec(src, ns)
    ns["execute"]()
    return ghi


class TestP206(unittest.TestCase):
    def test_chuyen_qua_engine_dung_nguoi(self):
        g = _chay({"fulfillment_status": "In Progress", "fulfillment_owner": "lam.nguyen@ecentric.vn"})
        self.assertEqual(g["reassign"], [("EC AI Topup Request", "EC-AITOP-2026-00029",
                                          "dong.diep@ecentric.vn", "hoan.tran@ecentric.vn")])
        self.assertEqual(g["set_value"], [], "set_value tay: ToDo cu con mo, nguoi moi khong co viec")

    def test_da_thuoc_dong_diep_thi_bo_qua(self):
        g = _chay({"fulfillment_status": "In Progress", "fulfillment_owner": "dong.diep@ecentric.vn"})
        self.assertEqual(g["reassign"], [])

    def test_da_hoan_tat_thi_khong_hoi_sinh(self):
        g = _chay({"fulfillment_status": "Completed", "fulfillment_owner": "lam.nguyen@ecentric.vn"})
        self.assertEqual(g["reassign"], [])

    def test_loi_engine_khong_lam_chet_migrate(self):
        g = _chay({"fulfillment_status": "In Progress", "fulfillment_owner": "lam.nguyen@ecentric.vn"},
                  loi_engine=True)
        self.assertTrue(any("FAILED" in str(x) for x in g["log"]))


if __name__ == "__main__":
    unittest.main()
