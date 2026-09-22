# Copyright (c) 2026, eCentric and contributors
"""Phieu da bi tra ve "cho bo sung" thi cap duyet KHONG con nut nao.

Hoan bao 22/09 tren EC-CTR-2026-00017: Finance tra ve luc 15:16, phieu o trang thai
"Information Required", ma bay nguoi duyet cap 2 van thay du ba nut Duyet / Tu choi /
Yeu cau bo sung.

Goc: `capabilities._pending_row` coi "Information Required" la trang thai MO, va
`derive` chi hoi "co dong duyet Pending o cap hien tai khong" - khong cho nao soi
`approval_status`. Bien `open_request` ngay duoi da tinh dung dieu can biet nhung chi
dung cho `can_cancel`; cung ho voi loi `readRoute` 15/09 (gia tri tinh ra roi bo roi).

Bo test nay giu hai dieu:
  1. Ba kha nang tat khi phieu dang "Information Required", va BAT lai khi ve "Pending".
     Nguoi de nghi thi nguoc lai - ho moi la nguoi phai ra tay.
  2. Luat do KHONG chi song o giao dien. Engine phai chan ca ba, vi mot luat chi co o
     man hinh la mot luat khong ton tai: goi thang API van di qua.
"""
import io
import os
import re
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CAP = os.path.join(_HERE, "..", "..", "shared", "requests", "capabilities.py")
_TRANS = os.path.join(_HERE, "..", "..", "shared", "workflow", "transitions.py")


def _nap_capabilities(dong_pending=True):
    """Nap mot BAN SAO RIENG cua capabilities.py voi frappe gia.

    Ban sao rieng, khong reload ban dung chung: reload ghi de ca thuoc tinh cua goi cha,
    va bo test khac co the dang cam mot ban gia cung ten o do (da dinh bay nay 16/09)."""
    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user="nguoiduyet@e.c")
    fr._ = lambda s: s
    fr.db = types.SimpleNamespace(
        exists=lambda dt, f=None: dong_pending,
        get_value=lambda *a, **k: None,
        count=lambda *a, **k: 0)
    fr.get_all = lambda *a, **k: []
    fr.get_roles = lambda *a, **k: []
    fr.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda f: False)
    fr.throw = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("throw"))
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda: ""
    fr.get_doc = lambda *a, **k: types.SimpleNamespace()
    fr.get_cached_doc = lambda *a, **k: types.SimpleNamespace()
    cu_frappe = sys.modules.get("frappe")
    sys.modules["frappe"] = fr
    try:
        import importlib.util
        _nap_capabilities.dem = getattr(_nap_capabilities, "dem", 0) + 1
        spec = importlib.util.spec_from_file_location(
            "_cap_rieng_%d" % _nap_capabilities.dem, _CAP)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if cu_frappe is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = cu_frappe
    return mod


def _phieu(status, muc=2):
    return types.SimpleNamespace(name="EC-APR-1", approval_status=status,
                                 current_level=muc, reference_doctype="EC Contract Review Request",
                                 reference_name="EC-CTR-1")


def _biz(nguoi_de_nghi="nguoide@e.c"):
    return types.SimpleNamespace(requested_by=nguoi_de_nghi, name="EC-CTR-1",
                                 doctype="EC Contract Review Request")


class TestNutCuaCapDuyet(unittest.TestCase):
    def test_tra_ve_cho_bo_sung_thi_TAT_ca_ba_nut(self):
        cap = _nap_capabilities(dong_pending=True)
        c = cap.derive("nguoiduyet@e.c", _biz(), _phieu("Information Required"))
        for k in ("can_approve", "can_reject", "can_request_information"):
            self.assertFalse(c[k], k + " van bat khi phieu dang cho nguoi de nghi bo sung")

    def test_ve_lai_Pending_thi_BAT_lai_ca_ba(self):
        cap = _nap_capabilities(dong_pending=True)
        c = cap.derive("nguoiduyet@e.c", _biz(), _phieu("Pending"))
        for k in ("can_approve", "can_reject", "can_request_information"):
            self.assertTrue(c[k], k + " khong bat lai khi nguoi de nghi da gui lai - siet qua tay")

    def test_khong_phai_nguoi_duyet_thi_van_khong_co_nut(self):
        cap = _nap_capabilities(dong_pending=False)
        c = cap.derive("nguoila@e.c", _biz(), _phieu("Pending"))
        self.assertFalse(c["can_approve"])

    def test_nguoi_DE_NGHI_moi_la_nguoi_phai_ra_tay(self):
        cap = _nap_capabilities(dong_pending=False)
        c = cap.derive("nguoide@e.c", _biz("nguoide@e.c"), _phieu("Information Required"))
        self.assertTrue(c["can_edit"], "nguoi de nghi phai sua duoc")
        self.assertTrue(c["can_resubmit"], "nguoi de nghi phai gui lai duoc")
        self.assertFalse(c["can_approve"])

    def test_phieu_Pending_nguoi_de_nghi_KHONG_tu_duyet_duoc(self):
        cap = _nap_capabilities(dong_pending=False)
        c = cap.derive("nguoide@e.c", _biz("nguoide@e.c"), _phieu("Pending"))
        self.assertFalse(c["can_approve"])
        self.assertFalse(c["can_resubmit"], "chua bi tra ve thi khong co gi de gui lai")


class TestEngineCungChan(unittest.TestCase):
    """Mot luat chi song o giao dien la mot luat khong ton tai - goi thang API van di qua."""

    def setUp(self):
        self.src = io.open(_TRANS, encoding="utf-8").read()

    def _than(self, ten):
        i = self.src.index("def %s(request_name" % ten)
        j = self.src.index("\ndef ", i + 10)
        return self.src[i:j]

    def test_ca_ba_duong_ghi_deu_co_chot(self):
        for ten in ("approve", "reject", "request_information"):
            than = self._than(ten)
            self.assertIn('req.approval_status == "Information Required"', than,
                          "%s() thieu chot - goi thang API se di qua" % ten)
            self.assertIn("frappe.throw", than, "%s() co kiem nhung khong nem loi" % ten)

    def test_chot_nam_SAU_khi_doc_lai_trang_thai_co_khoa(self):
        """Doc truoc khoa la tin don; sau khoa moi la su that (bai hoc 31/08 trong chinh file)."""
        for ten in ("approve", "reject", "request_information"):
            than = self._than(ten)
            doc_lai = than.index('req.approval_status = frappe.db.get_value(')
            chot = than.index('if req.approval_status == "Information Required":')
            self.assertGreater(chot, doc_lai,
                               "%s(): chot dat TRUOC luc doc lai trang thai co khoa" % ten)


class TestHubCungLuat(unittest.TestCase):
    def test_nut_nhanh_tren_hub_hoi_dung_Pending(self):
        p = os.path.join(_HERE, "..", "..", "reporting", "service.py")
        src = io.open(p, encoding="utf-8").read()
        m = re.search(r'v\["can_approve"\] = bool\((.{0,120})', src, re.S)
        self.assertIsNotNone(m)
        self.assertIn('"Pending"', m.group(1),
                      "hub van dung is_open -> nut nhanh bat tren phieu da bi tra ve")


if __name__ == "__main__":
    unittest.main()
