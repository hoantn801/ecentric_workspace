# Copyright (c) 2026, eCentric and contributors
"""Test luat bo cap cua phieu ty trong luong brand - chay khong can bench.

Doc file nguon that va inject fake reader/resolver qua constructor (rule 13). KHONG
copy logic sang day: neu copy thi ban copy pass con production van sai - dung cai bay
da tung xay ra voi ec_hr_leave_pending."""
import sys
import types
import unittest


class _Throw(Exception):
    pass


def _stub_frappe():
    m = types.ModuleType("frappe")
    m.throw = lambda msg, exc=None: (_ for _ in ()).throw(_Throw(msg))

    def _t(s):
        return s
    m._ = _t
    utils = types.ModuleType("frappe.utils")
    utils.flt = lambda v, p=2: round(float(v), p)
    m.utils = utils
    sys.modules["frappe"] = m
    sys.modules["frappe.utils"] = utils
    # chan import that cua engine - test nay chi kiem luat bo cap
    for name in ("ecentric_workspace", "ecentric_workspace.approval_center",
                 "ecentric_workspace.approval_center.shared",
                 "ecentric_workspace.approval_center.shared.workflow"):
        sys.modules.setdefault(name, types.ModuleType(name))
    tr = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    tr.resolve_department_manager_user = lambda d: None
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = tr
    for name in ("ecentric_workspace.approval_center.features",
                 "ecentric_workspace.approval_center.features.brand_weight",
                 "ecentric_workspace.approval_center.features.brand_weight.infrastructure"):
        sys.modules.setdefault(name, types.ModuleType(name))
    rd = types.ModuleType(
        "ecentric_workspace.approval_center.features.brand_weight.infrastructure.employee_reader")
    rd.lead_user = lambda e: None
    sys.modules[
        "ecentric_workspace.approval_center.features.brand_weight.infrastructure.employee_reader"] = rd
    return m


_stub_frappe()
import importlib.util
import os

_SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                    "features", "brand_weight", "application", "routing.py")
_spec = importlib.util.spec_from_file_location("_bw_routing", os.path.abspath(_SRC))
routing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(routing)


class _Reader:
    def __init__(self, lead):
        self._lead = lead

    def lead_user(self, employee):
        return self._lead


def _svc(lead, head):
    return routing.ResolveBrandWeightSkipLevelsService(
        reader=_Reader(lead), head_resolver=lambda d: head)


class TestLuatBoCap(unittest.TestCase):
    def test_binh_thuong_khong_bo_cap_nao(self):
        skip, _r = _svc("lead@x", "head@x").execute("EMP-1", "Service - EC", "nv@x")
        self.assertEqual(skip, [])

    def test_khong_co_lead_thi_bo_buoc_1(self):
        """CEO khong co reports_to. Giu buoc 1 la phieu treo vinh vien."""
        skip, reason = _svc(None, "head@x").execute("EMP-CEO", "Management - EC", "nv@x")
        self.assertEqual(skip, [1])
        self.assertIn("khong co quan ly truc tiep", reason)

    def test_lead_trung_nguoi_nop_thi_bo_buoc_1(self):
        skip, reason = _svc("nv@x", "head@x").execute("EMP-2", "Media - EC", "nv@x")
        self.assertEqual(skip, [1])
        self.assertIn("trung voi nguoi nop", reason)

    def test_truong_phong_tu_nop_thi_bo_buoc_2(self):
        skip, reason = _svc("lead@x", "nv@x").execute("EMP-3", "Service - EC", "nv@x")
        self.assertEqual(skip, [2])
        self.assertIn("chinh la truong phong", reason)

    def test_khong_bao_gio_bo_ca_hai_cap(self):
        """Vua khong co lead vua la truong phong: giu buoc 2 de tu bam, khong bo het."""
        skip, reason = _svc(None, "nv@x").execute("EMP-CEO", "Management - EC", "nv@x")
        self.assertEqual(skip, [1])
        self.assertIn("khong bo ca hai cap", reason)

    def test_phong_chua_co_truong_phong_thi_nem_loi_ngay(self):
        """Fail to tieng luc nop, khong de phieu treo im nhu don cuoi phuong.nguyen."""
        with self.assertRaises(_Throw) as cm:
            _svc("lead@x", None).execute("EMP-4", "Service - EC", "nv@x")
        self.assertIn("chưa có trưởng phòng", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
