# Copyright (c) 2026, eCentric and contributors
"""Hub "Tat ca yeu cau": cap ky so phai co nut "Duyet & Ky", khong phai "Duyet" (p141).

04/09 Vinh bam "Duyet" tren 00053 trong popup hub -> engine tu choi "Cap duyet nay yeu cau ky
so. Vui long dung chuc nang 'Duyệt &amp; Ký'" - hub khong co nut do, va "&amp;" hien nguyen.

  1. capabilities.derive (code THAT, frappe gia): requires_signature chi hoi guard khi nguoi
     nay dang duoc duyet; guard hong -> False, khong vo popup.
  2. reporting.service (AST): dong danh sach mang requires_signature, tinh qua helper co memo
     va bat exception.
  3. query_service.detail tra business_doctype.
  4. hub HTML: popup doi nut theo cap.requires_signature -> approve_sign -> goi
     esign.api.approve_and_sign bang POST voi business_doctype/business_name; dong danh sach
     ky so thi mo popup; extractServerMsg giai ma entity.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_AC = os.path.join(_APP, "ecentric_workspace", "approval_center")


def _read(*parts):
    with io.open(os.path.join(_AC, *parts), encoding="utf-8") as fh:
        return fh.read()


def _capabilities(guard_result=True, guard_raises=False):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user="vinh.vu@ecentric.vn")
    fk.db = types.SimpleNamespace(get_value=lambda *a, **k: None, exists=lambda *a, **k: None)
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    fk.get_all = lambda *a, **k: []
    guard = types.ModuleType("ecentric_workspace.platform.esign.guard")
    guard.calls = []

    def level_requires_signature(dt, at, lvl, final_level=None, ignore_gates=False):
        guard.calls.append((dt, at, lvl, final_level))
        if guard_raises:
            raise RuntimeError("boom")
        return guard_result
    guard.level_requires_signature = level_requires_signature
    guard.request_final_level = lambda name: 4
    perms = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
    perms.can_view_request = lambda *a, **k: True
    mods = {"frappe": fk, "ecentric_workspace.platform.esign.guard": guard,
            "ecentric_workspace.approval_center.shared.workflow.permissions": perms}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        mod = types.ModuleType("_capabilities_under_test")
        exec(compile(_read("shared", "requests", "capabilities.py"), "capabilities.py", "exec"),
             mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    mod._guard = guard
    mod._mods = mods
    return mod


def _with(mods, fn):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestCapabilities(unittest.TestCase):
    def _req(self):
        return types.SimpleNamespace(name="AR-1", approval_type="PAYMENT_REQUEST", current_level=1,
                                     approval_status="Pending")

    def _biz(self):
        return types.SimpleNamespace(doctype="EC Payment Request")

    def test_dang_duoc_duyet_va_cap_ky_so(self):
        c = _capabilities(True)
        self.assertTrue(_with(c._mods, lambda: c._requires_signature(True, self._biz(), self._req())))
        self.assertEqual(c._guard.calls, [("EC Payment Request", "PAYMENT_REQUEST", 1, 4)])

    def test_khong_duoc_duyet_thi_khong_hoi_guard(self):
        c = _capabilities(True)
        self.assertFalse(_with(c._mods, lambda: c._requires_signature(False, self._biz(), self._req())))
        self.assertEqual(c._guard.calls, [])

    def test_guard_hong_thi_False_khong_nem(self):
        c = _capabilities(guard_raises=True)
        self.assertFalse(_with(c._mods, lambda: c._requires_signature(True, self._biz(), self._req())))

    def test_derive_tra_khoa_requires_signature(self):
        src = ast.unparse([n for n in ast.walk(ast.parse(_read("shared", "requests", "capabilities.py")))
                           if isinstance(n, ast.FunctionDef) and n.name == "derive"][0])
        self.assertIn("'requires_signature': _requires_signature(can_act, business_doc, approval_request)", src)


class TestListRowsAndDetail(unittest.TestCase):
    def test_dong_danh_sach_mang_requires_signature_qua_helper_co_memo(self):
        src = _read("reporting", "service.py")
        tree = ast.parse(src)
        helper = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "_requires_signature"][0]
        hs = ast.unparse(helper)
        self.assertIn("level_requires_signature(", hs)
        self.assertIn("except Exception", hs)
        self.assertIn("memo[key] = False", hs)
        self.assertIn("v['requires_signature'] = bool(v['can_approve'] and _requires_signature(", ast.unparse(tree))

    def test_detail_tra_business_doctype(self):
        self.assertIn("'business_doctype': definition.business_doctype",
                      ast.unparse(ast.parse(_read("shared", "requests", "query_service.py"))))


class TestHubHtml(unittest.TestCase):
    def setUp(self):
        self.h = _read("ui", "all_requests", "main_section.html")

    def test_popup_doi_nut_theo_requires_signature(self):
        self.assertIn('cap.requires_signature', self.h)
        self.assertIn('data-a="approve_sign">Duyệt &amp; Ký</button>', self.h)
        self.assertIn('data-a="approve">Duyệt</button>', self.h)

    def test_approve_sign_goi_esign_api_bang_POST_voi_doctype_va_name(self):
        i = self.h.index("function runApproveSign")
        body = self.h[i:i + 1500]
        self.assertIn('method:"ecentric_workspace.platform.esign.api.approve_and_sign"', body)
        self.assertIn('type:"POST"', body)
        self.assertIn("business_doctype:d.business_doctype", body)
        self.assertIn("business_name:d.business_name", body)
        self.assertIn('d.business_name!==reqName', body, "phai ky dung phieu dang mo")
        self.assertIn('kind==="approve_sign"', self.h)

    def test_dong_danh_sach_cap_ky_so_mo_popup(self):
        self.assertIn('r.requires_signature', self.h)
        self.assertIn('data-qa="open"', self.h)
        self.assertIn('if(kind==="open"){ openDetail(reqName); return; }', self.h)

    def test_thong_diep_may_chu_giai_ma_entity(self):
        i = self.h.index("function extractServerMsg")
        self.assertIn('ta.innerHTML=t; t=ta.value', self.h[i:i + 700])


if __name__ == "__main__":
    unittest.main()
