# Copyright (c) 2026, eCentric and contributors
"""Hai loi Hoan bao 04/09 ngay sau p137 (xem p139).

1. #ecdStage phai duoc bat lai bang "inline-block", khong phai "" (gan "" = xoa inline style
   -> block -> canvas lech 58px so voi overlay -> dai ben phai trang khong dat o duoc).
2. Phieu chua gui: readiness phai suy ra loai yeu cau tu profile duy nhat dang bat khi
   `approval_type` trong - de o ket noi SCTS hien TRUOC khi bam Gui. Chay code THAT cua
   requester._draft_approval_type voi frappe gia.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


class TestStageInlineBlock(unittest.TestCase):
    def test_stage_bat_lai_bang_inline_block(self):
        h = _read("ui/document_signing_section.html")
        self.assertIn('getElementById("ecdStage").style.display = canPdf ? "inline-block" : "none"', h)
        self.assertNotIn('getElementById("ecdStage").style.display = canPdf ? "" : "none"', h)
        # inline style goc van la inline-block (de lan dau mo cung dung)
        self.assertIn('id="ecdStage" style="position:relative;display:inline-block"', h)


def _requester(profiles, approval_type_on_doc=None, has_col=True):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.get_all = lambda dt, filters=None, pluck=None, limit_page_length=None, **k: \
        [p for p in profiles][:limit_page_length]
    fk.db = types.SimpleNamespace(
        get_value=lambda dt, name, field=None, **k: approval_type_on_doc,
        has_column=lambda dt, col: has_col)
    fk.session = types.SimpleNamespace(user="x")
    utils = types.ModuleType("frappe.utils"); utils.now_datetime = lambda: None
    stubs = {}
    for n in ("events", "guard", "hashing", "package", "permissions"):
        stubs["ecentric_workspace.platform.esign." + n] = types.ModuleType(n)
    mods = {"frappe": fk, "frappe.utils": utils}
    mods.update(stubs)
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        for k in list(sys.modules):
            if k.startswith("ecentric_workspace.platform.esign") and k not in mods:
                sys.modules.pop(k)
        mod = types.ModuleType("_requester_under_test")
        exec(compile(_read("requester.py"), "requester.py", "exec"), mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod


class TestDraftApprovalType(unittest.TestCase):
    def test_truong_tren_phieu_co_thi_dung(self):
        r = _requester(["PAYMENT_REQUEST"], approval_type_on_doc="X")
        self.assertEqual(r._draft_approval_type("EC Payment Request", "PR-1"), "X")

    def test_trong_va_dung_mot_profile_thi_lay_cua_profile(self):
        r = _requester(["PAYMENT_REQUEST"], approval_type_on_doc=None)
        self.assertEqual(r._draft_approval_type("EC Payment Request", "PR-1"), "PAYMENT_REQUEST")

    def test_nhieu_profile_thi_khong_doan(self):
        r = _requester(["A", "B"], approval_type_on_doc=None)
        self.assertIsNone(r._draft_approval_type("EC Payment Request", "PR-1"))

    def test_khong_profile_thi_None(self):
        r = _requester([], approval_type_on_doc=None)
        self.assertIsNone(r._draft_approval_type("EC Payment Request", "PR-1"))

    def test_readiness_va_link_context_deu_dung_ham_nay(self):
        tree = ast.parse(_read("requester.py"))
        for fn_name in ("requester_signing_readiness", "link_context"):
            fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name][0]
            self.assertIn("_draft_approval_type(", ast.unparse(fn), fn_name)


# ------------------------------------------------------------- nut "Ket noi SCTS" tren hub (p140)
_HUB = os.path.join(_APP, "ecentric_workspace", "approval_center", "ui", "hub", "main_section.html")


class TestHubSctsButton(unittest.TestCase):
    def setUp(self):
        with io.open(_HUB, encoding="utf-8") as fh:
            self.h = fh.read()

    def test_nut_va_popover_co_mat_va_an_mac_dinh(self):
        self.assertIn('id="apc-scts" hidden', self.h)
        self.assertIn('id="apc-scts-btn"', self.h)
        self.assertIn('id="apc-scts-form"', self.h)
        self.assertIn('type="password"', self.h)

    def test_goi_dung_endpoint_me_bang_POST_va_xoa_mat_khau_truoc_khi_gui(self):
        i = self.h.index("api.link_scts_account_me")
        self.assertIn('type:"POST"', self.h[i:i + 120].replace(" ", ""))
        self.assertIn('$("apc-scts-pass").value=""', self.h[:i][-600:])
        self.assertIn("api.scts_link_status_me", self.h)

    def test_hien_theo_backend_khong_tu_suy(self):
        self.assertIn("st.needs_link && st.has_mapping", self.h)
        self.assertIn("sctsInit();", self.h)

    def test_api_me_chi_session_user_va_POST(self):
        tree = ast.parse(_read("api.py"))
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for name in ("link_scts_account_me", "unlink_scts_account_me"):
            fn = fns[name]
            decos = [ast.unparse(d) for d in fn.decorator_list]
            self.assertTrue(any("POST" in d for d in decos), name)
            self.assertNotIn("user", [a.arg for a in fn.args.args], name)
            self.assertIn("frappe.session.user", ast.unparse(fn), name)
        self.assertIn("form_dict.pop('password'", ast.unparse(fns["link_scts_account_me"]))
        self.assertIn("frappe.session.user", ast.unparse(fns["scts_link_status_me"]))

    def test_default_context_khong_doan_khi_nhieu_hoac_khong_co_settings(self):
        src = ast.unparse([n for n in ast.walk(ast.parse(_read("user_link.py")))
                           if isinstance(n, ast.FunctionDef) and n.name == "default_context"][0])
        self.assertIn("if len(rows) != 1:", src)
        self.assertIn("'integration_enabled': 1", src)

    def test_hub_page_sync_chap_nhan_live_sha_da_do(self):
        with io.open(os.path.join(_APP, "ecentric_workspace", "approval_center", "ui", "hub",
                                  "page_sync.py"), encoding="utf-8") as fh:
            ps = fh.read()
        self.assertIn('"0a0283916444d73cbebb401f89146a9235e0a89268ba34dda68235120b055a81"', ps)
        import hashlib
        new = hashlib.sha256(self.h.replace("\r\n", "\n").encode("utf-8")).hexdigest()
        self.assertIn('BASELINE_SHA256 = "%s"' % new, ps, "BASELINE phai la sha cua HTML dang ship")
        self.assertNotIn("force=1", _read_patch("p140_resync_hub_scts_link_button.py"))


def _read_patch(name):
    with io.open(os.path.join(_APP, "ecentric_workspace", "approval_center", "patches", name),
                 encoding="utf-8") as fh:
        return fh.read()


if __name__ == "__main__":
    unittest.main()
