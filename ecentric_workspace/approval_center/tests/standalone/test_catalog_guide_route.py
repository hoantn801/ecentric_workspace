# Copyright (c) 2026, eCentric and contributors
"""Danh muc Approval Center noi cho trang biet the nao co bai huong dan.

Trang KHONG duoc tu doan. Neu icon "?" duoc ve theo mot danh sach ma cung viet
trong JS thi ngay them bai thu hai la hai ban sao lech nhau, va kieu lech nay im
lang: the tro toi mot route khong ton tai, khong loi, khong ai bao.

Nen `list_catalog` phai kem `guide_route` / `guide_title` lay tu
guides.registry - mot cho khai duy nhat. Test nay chay `_shape` THAT (nap bang
exec voi mot frappe gia, nen khong can site) chu khong grep source: mot phep
kiem chi khang dinh "co goi ham" thi refactor mot cai la no mu.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))     # .../ecentric_workspace
_REPO = os.path.dirname(_APP)
sys.path.insert(0, _REPO)

from ecentric_workspace.guides import registry as guides_registry   # noqa: E402


class _Row(dict):
    """Hang cua frappe.get_all: doc duoc bang ca . lan []."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            return None


def _catalog_module():
    """Nap catalog_api voi frappe gia. exec(compile(...)) chu khong import: tranh
    __pycache__ lam hong phep thu dot bien (bai hoc 31/08)."""
    fk = types.ModuleType("frappe")
    fk.utils = types.ModuleType("frappe.utils")
    fk.utils.getdate = lambda v=None: v
    fk.utils.nowdate = lambda: "2026-09-08"
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.session = types.SimpleNamespace(user="x@ecentric.vn")
    fk.get_all = lambda *a, **k: []

    perms = types.ModuleType("perms")
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = fk
    sys.modules["frappe.utils"] = fk.utils
    try:
        src = io.open(os.path.join(_APP, "approval_center", "shared", "catalog_api.py"),
                      encoding="utf-8").read()
        mod = types.ModuleType("catalog_api_under_test")
        mod.__dict__["perms"] = perms
        exec(compile(src, "catalog_api.py", "exec"), mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


_MOD = _catalog_module()


def _shape(code, title="X"):
    t = _Row(name=code, approval_title=title, description="", icon=None, category="CAT",
             card_status="Active", process_status=None, route="/approvals/x", sort_order=1)
    cat = _Row(category_name="Danh muc", icon=None, sort_order=1)
    return _MOD._shape(t, cat)


class TestTheMangTheoBaiHuongDan(unittest.TestCase):
    def test_loai_co_bai_thi_tra_route_va_ten_ngan(self):
        g = guides_registry.guide_for_approval_type("PAYMENT_REQUEST")
        self.assertIsNotNone(g, "du lieu goc doi roi - sua test truoc khi sua code")
        out = _shape("PAYMENT_REQUEST")
        self.assertEqual(out["guide_route"], g["route"])
        self.assertEqual(out["guide_title"], g["short"])

    def test_ca_hai_form_cua_mot_quy_trinh_deu_tro_ve_cung_bai(self):
        a = _shape("PURCHASE_REQUEST")["guide_route"]
        b = _shape("PAYMENT_REQUEST")["guide_route"]
        self.assertEqual(a, b)
        self.assertTrue(a.startswith(guides_registry.ROUTE_PREFIX + "/"))

    def test_loai_chua_co_bai_thi_None_chu_khong_phai_chuoi_rong(self):
        """None de JS `if(c.guide_route)` tat icon. Chuoi rong cung tat, nhung mot
        route rong lot vao href thi bam ra chinh trang dang dung - kho hieu hon
        han khong co icon."""
        out = _shape("LEAVE")
        self.assertIsNone(out["guide_route"])
        self.assertIsNone(out["guide_title"])

    def test_khong_lam_hong_cac_truong_cu(self):
        out = _shape("PAYMENT_REQUEST", title="Đề nghị thanh toán")
        for f in ("approval_code", "approval_title", "card_status", "route",
                  "category_name", "sort_order"):
            self.assertIn(f, out)
        self.assertEqual(out["approval_code"], "PAYMENT_REQUEST")


if __name__ == "__main__":
    unittest.main()
