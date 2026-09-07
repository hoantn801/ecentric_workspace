# Copyright (c) 2026, eCentric and contributors
"""Hub "Nhap cua toi": nut Huy ban nhap (07/09, Hoan - nhap khong dung thi thanh rac).

reporting.actions.discard_draft la BO DINH TUYEN: nhan (approval_type, name) nhu my_drafts
tra ra, kiem quyen chu phieu TRUOC khi noi gi ve trang thai (name do client gui, ma tuan
tu doan duoc), chi chap nhan dung ban nhap (docstatus 0, chua approval_request), roi giao
cho facade.cancel - cung duong voi "Huy yeu cau" tren form (don goi ky nhap + xoa mem).

Code THAT cua actions.py nap bang exec(compile) tren frappe gia; hub HTML kiem landmark
nut + goi dung endpoint bang POST.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))


def _read(*p):
    with io.open(os.path.join(_AC, *p), encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


class _PermErr(_Throw):
    pass


class _NotFound(_Throw):
    pass


def _actions(row, user="hien@ec.vn", roles=("Employee",)):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)
    fk.PermissionError = _PermErr
    fk.DoesNotExistError = _NotFound
    fk.get_roles = lambda u=None: list(roles)
    fk.whitelist = lambda *a, **k: (lambda f: f)
    fk.log_error = lambda *a, **k: None
    fk.get_meta = lambda *a, **k: types.SimpleNamespace(fields=[])
    fk.utils = types.SimpleNamespace()
    fk.db = types.SimpleNamespace(
        get_value=lambda dt, name, fields=None, as_dict=False, **k:
            (types.SimpleNamespace(**row) if row else None),
        exists=lambda *a, **k: None, get_all=lambda *a, **k: [])
    fk.get_all = lambda *a, **k: []

    def throw(msg, exc=_Throw):   # frappe.throw mac dinh = ValidationError; o day la _Throw
        raise exc(msg)
    fk.throw = throw

    facade_calls = []
    facade_mod = types.ModuleType("ecentric_workspace.approval_center.shared.facade")
    facade_mod.APPROVAL_FACADE = types.SimpleNamespace(
        cancel=lambda definition, name, reason: (facade_calls.append((definition.code, name, reason))
                                                 or {"deleted": True}))
    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    defs = {"CONTRACT_REVIEW": types.SimpleNamespace(code="CONTRACT_REVIEW",
                                                     business_doctype="EC Contract Review")}

    def get_definition(code):
        try:
            return defs[code]
        except KeyError:
            raise KeyError(code) from None
    reg.get_definition = get_definition
    vi = types.ModuleType("ecentric_workspace.approval_center.shared.vi_display")
    caps = types.ModuleType("ecentric_workspace.approval_center.shared.requests.capabilities")
    caps.is_system_manager = lambda u=None: "System Manager" in roles
    mods = {"frappe": fk, "ecentric_workspace.approval_center.shared.facade": facade_mod,
            "ecentric_workspace.approval_center.shared.registry": reg,
            "ecentric_workspace.approval_center.shared.vi_display": vi,
            "ecentric_workspace.approval_center.shared.requests.capabilities": caps}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_actions_under_test")
        exec(compile(_read("reporting", "actions.py"), "actions.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._facade_calls = facade_calls
    return m


DRAFT = {"docstatus": 0, "approval_request": None, "requested_by": "hien@ec.vn"}


class TestDiscardDraft(unittest.TestCase):
    def test_chu_phieu_huy_ban_nhap_di_qua_facade_cancel(self):
        m = _actions(dict(DRAFT))
        out = m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-00010")
        self.assertEqual(out, {"deleted": True})
        self.assertEqual(m._facade_calls, [("CONTRACT_REVIEW", "EC-CTR-2026-00010", None)])

    def test_khong_phai_chu_phieu_thi_khong_tim_thay_va_khong_lo_trang_thai(self):
        m = _actions(dict(DRAFT), user="ke.la@ec.vn")
        with self.assertRaises(_NotFound):
            m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-00010")
        self.assertEqual(m._facade_calls, [])
        # cung phieu da gui duyet: nguoi la van chi thay "khong tim thay", khong thay "da gui duyet"
        m = _actions(dict(DRAFT, approval_request="EC-APR-2026-00001"), user="ke.la@ec.vn")
        with self.assertRaises(_NotFound):
            m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-00010")

    def test_system_manager_duoc_huy_ho(self):
        m = _actions(dict(DRAFT), user="admin@ec.vn", roles=("System Manager",))
        m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-00010")
        self.assertEqual(len(m._facade_calls), 1)

    def test_phieu_da_gui_duyet_thi_tu_choi(self):
        for row in (dict(DRAFT, approval_request="EC-APR-2026-00001"), dict(DRAFT, docstatus=1)):
            m = _actions(row)
            with self.assertRaises(_Throw) as cm:
                m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-00010")
            self.assertNotIsInstance(cm.exception, _NotFound)
            self.assertIn("đã gửi duyệt", str(cm.exception))
            self.assertEqual(m._facade_calls, [])

    def test_khong_co_phieu_hoac_loai_la_thi_tu_choi(self):
        m = _actions(None)
        with self.assertRaises(_NotFound):
            m.discard_draft("CONTRACT_REVIEW", "EC-CTR-2026-09999")
        m = _actions(dict(DRAFT))
        with self.assertRaises(_Throw):
            m.discard_draft("KHONG_CO", "EC-CTR-2026-00010")
        self.assertEqual(m._facade_calls, [])

    def test_endpoint_chi_nhan_POST(self):
        src = _read("reporting", "actions.py")
        i = src.index("def discard_draft(")
        head = src[:i].rstrip().splitlines()[-1]
        self.assertIn('@frappe.whitelist(methods=["POST"])', head)


class TestHubHtml(unittest.TestCase):
    def setUp(self):
        self.h = _read("ui", "all_requests", "main_section.html")

    def test_dai_nhap_co_nut_huy_va_goi_dung_endpoint_bang_POST(self):
        i = self.h.index("function draftsHtml()")
        block = self.h[i:self.h.index("function renderError()")]
        self.assertIn('data-discard="', block)
        self.assertIn("function discardDraft(", block)
        self.assertIn("reporting.actions.discard_draft", block)
        self.assertIn('type:"POST"', block)
        self.assertIn("window.confirm(", block)                       # hoi lai truoc khi xoa
        self.assertIn("approval_type:type, name:name", block)

    def test_nut_huy_duoc_noi_ca_khi_danh_sach_rong(self):
        # render() nhanh rong tra ve som - truoc 07/09 khong goi wire() nen nut trong dai
        # nhap chet khi tab khong co dong nao.
        i = self.h.index("function render(rows)")
        line = [l for l in self.h[i:i + 1200].splitlines() if "if(!rows.length)" in l][0]
        self.assertIn("wire();", line)
        j = self.h.index("function wire()")
        self.assertIn("[data-discard]", self.h[j:j + 800])


if __name__ == "__main__":
    unittest.main()
