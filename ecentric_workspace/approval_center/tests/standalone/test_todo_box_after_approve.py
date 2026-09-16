# Copyright (c) 2026, eCentric and contributors
"""Hop "Cho toi xu ly": duyet xong thi dong phai roi khoi hop.

Anh Lam bao 16/09: "moi lan a duyet xong thi no ko bien mat ngay". Do tren production:
duyet cap cuoi luc 16:57:03.526 -> 51ms sau phieu nghiep vu mang fulfillment_status
='Assigned'. Dong vua roi khoi ve "cho toi duyet" thi rot NGAY vao ve "viec fulfilment
cua toi" cua CUNG mot hop, nen nhin nhu khong co gi xay ra.

Nguyen nhan: `_fulfillment_refs` hoi `is_eligible_fulfiller(...)` khong kem `business_name`,
o dang do ham con duong "co mot ToDo mo BAT KY tren loai phieu nay" - ma nguoi duyet luc nao
cung co ToDo mo tren loai do, vi day chinh la cach giao viec duyet.

Bo test nay giu hai dieu:
  1. Mot ToDo DUYET khong bien nguoi ta thanh NGUOI XU LY.
  2. Khong nap duoc module quyen thi hop RONG, khong phai hop day. Mac dinh mo tren du lieu
     thanh toan la mot lua chon sai, khong phai mot danh doi.
"""
import sys
import types
import unittest


def _nap(quyen=None, todo_mo=True):
    """Nap queries voi frappe + permissions gia. `quyen` = module quyen (None = khong nap duoc)."""
    ghi = {"hoi": []}

    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user="lam@e.c")

    class _Meta:
        def has_field(self, f):
            return f == "fulfillment_status"
    fr.get_meta = lambda dt: _Meta()

    def _get_all(dt, **k):
        f = k.get("filters") or {}
        if f.get("fulfillment_status") == "In Progress":
            return []                       # anh Lam khong giu viec nao
        if f.get("fulfillment_status") == "Assigned":
            return ["EC-PAYR-2026-00144", "EC-PAYR-2026-00140"]
        return []
    fr.get_all = _get_all
    fr.db = types.SimpleNamespace(exists=lambda *a, **k: todo_mo)
    sys.modules["frappe"] = fr

    def _dat(ten, mod):
        """Dat module gia vao CA sys.modules LAN thuoc tinh cua goi cha.

        `from goi import ten` lay THUOC TINH cua goi cha truoc, khong doc sys.modules. Neu
        mot bai test truoc do da nap module that thi thuoc tinh do van tro vao ban that va
        ban gia bi bo qua - bo test xanh khi chay le, do khi chay ca file. Da dinh dung bay
        nay o test_all_tab_scope 16/09; ghi lai de khong dinh lan ba.
        """
        sys.modules[ten] = mod
        cha, _, la = ten.rpartition(".")
        if cha in sys.modules:
            setattr(sys.modules[cha], la, mod)

    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    reg.APPROVAL_DEFINITIONS = {
        "PAYMENT_REQUEST": types.SimpleNamespace(
            code="PAYMENT_REQUEST", business_doctype="EC Payment Request")}
    _dat(reg.__name__, reg)

    perm_name = "ecentric_workspace.approval_center.shared.workflow.permissions"
    if quyen is None:
        # `sys.modules[x] = None` lam chinh lenh import x nem ImportError -> _perm = None,
        # tuc DUNG duong ma nhanh fail-open di qua. Dat mot module "hong" thi import VAN
        # thanh cong va duong do khong bao gio duoc chay thu.
        cha, _, la = perm_name.rpartition(".")
        if cha in sys.modules and hasattr(sys.modules[cha], la):
            delattr(sys.modules[cha], la)
        sys.modules[perm_name] = None
    else:
        _dat(perm_name, quyen)

    import importlib
    from ecentric_workspace.approval_center.reporting import queries
    importlib.reload(queries)
    return queries, ghi


def _quyen(co_todo_mo=True, la_SM=False, la_fulfiller_cau_hinh=False):
    m = types.ModuleType(
        "ecentric_workspace.approval_center.shared.workflow.permissions")

    def _cu(user, approval_type=None, business_doctype=None, business_name=None):
        """Ban CU: mot ToDo mo bat ky tren LOAI phieu cung tinh la nguoi xu ly."""
        return bool(la_SM or la_fulfiller_cau_hinh or (co_todo_mo and business_doctype))

    def _moi(user=None, approval_type=None, fulfillment_owner=None):
        """Ban DUNG: khong co duong ToDo."""
        return bool(la_SM or la_fulfiller_cau_hinh)
    m.is_eligible_fulfiller = _cu
    m.is_eligible_fulfiller_without_todo = _moi
    return m


class TestToDoDuyetKhongPhaiViecXuLy(unittest.TestCase):
    def test_nguoi_duyet_co_todo_mo_KHONG_thay_viec_chua_ai_nhan(self):
        q, _ = _nap(_quyen(co_todo_mo=True))
        refs = q._fulfillment_refs("lam@e.c")
        self.assertEqual(refs, [],
                         "mot ToDo DUYET dang bien anh Lam thanh nguoi xu ly - dung cai lam "
                         "phieu vua duyet khong roi khoi hop")

    def test_fulfiller_duoc_cau_hinh_VAN_thay(self):
        q, _ = _nap(_quyen(co_todo_mo=False, la_fulfiller_cau_hinh=True))
        self.assertEqual(len(q._fulfillment_refs("ketoan@e.c")), 2,
                         "siet qua tay: nguoi that su xu ly phai con thay viec cua ho")

    def test_system_manager_van_thay(self):
        q, _ = _nap(_quyen(co_todo_mo=False, la_SM=True))
        self.assertEqual(len(q._fulfillment_refs("admin@e.c")), 2)

    def test_khong_nap_duoc_module_quyen_thi_HOP_RONG(self):
        q, _ = _nap(quyen=None)
        self.assertEqual(q._fulfillment_refs("ai@e.c"), [],
                         "fail-open: loi import lam MOI phieu chua ai nhan lot vao hop MOI nguoi")

    def test_khong_co_nguoi_thi_khong_tra_gi(self):
        q, _ = _nap(_quyen(la_SM=True))
        self.assertEqual(q._fulfillment_refs(None), [])


class TestNguonMa(unittest.TestCase):
    def test_khong_con_goi_ban_long_leo(self):
        import io
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, "..", "..", "reporting", "queries.py")
        src = io.open(p, encoding="utf-8").read()
        i = src.index("def _fulfillment_refs")
        j = src.index("\ndef ", i + 10)
        than = src[i:j]
        self.assertNotIn("_perm.is_eligible_fulfiller(", than,
                         "quay lai ban co duong ToDo long leo")
        self.assertIn("is_eligible_fulfiller_without_todo", than)
        self.assertIn("eligible = False", than, "mac dinh phai la dong")


if __name__ == "__main__":
    unittest.main()
