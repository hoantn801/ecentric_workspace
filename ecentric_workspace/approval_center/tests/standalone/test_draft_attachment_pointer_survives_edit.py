# Copyright (c) 2026, eCentric and contributors
"""Da tai tep o "Tai lieu & Ky so" ma bam Gui van bao thieu tep (Hoan 07/09).

Con tro `request_attachment` do KHOI KY SO dat len server SAU khi form nap. Hai lo:
  1. server: save_draft nhan `request_attachment: ""` tu form cu -> XOA con tro
     (command_service._blank_attach_would_wipe: rong tu form = khong doi, cho truong Attach).
  2. client: "Tiep tuc chinh sua" mo form tu `det` cu -> validateSubmit bat thieu tep.
     startEditDraft nap get_detail MOI; khoi ky so bao payr:attachments-changed sau khi tai;
     form dang mo cap nhat state.draft.request_attachment.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_PKG = os.path.join(_APP, "ecentric_workspace")


def _read(*parts):
    with io.open(os.path.join(_PKG, *parts), encoding="utf-8") as fh:
        return fh.read()


def _fn():
    src = _read("approval_center", "shared", "requests", "command_service.py")
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_blank_attach_would_wipe"]
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "cs.py", "exec"), ns)
    return ns["_blank_attach_would_wipe"]


def _doc(current, fieldtype):
    meta = types.SimpleNamespace(get_field=lambda f: types.SimpleNamespace(fieldtype=fieldtype))
    return types.SimpleNamespace(get=lambda f: current, meta=meta)


class TestBlankAttach(unittest.TestCase):
    def test_attach_rong_khong_xoa_gia_tri_cu(self):
        f = _fn()
        self.assertTrue(f(_doc("/private/files/a.pdf", "Attach"), "request_attachment", ""))
        self.assertTrue(f(_doc("/private/files/a.pdf", "Attach"), "request_attachment", None))

    def test_gia_tri_moi_van_ghi(self):
        f = _fn()
        self.assertFalse(f(_doc("/private/files/a.pdf", "Attach"), "request_attachment", "/private/files/b.pdf"))

    def test_truong_khong_phai_attach_van_xoa_duoc(self):
        f = _fn()
        self.assertFalse(f(_doc("abc", "Data"), "reason", ""))

    def test_chua_co_gia_tri_thi_khong_can_giu(self):
        f = _fn()
        self.assertFalse(f(_doc("", "Attach"), "request_attachment", ""))

    def test_save_draft_dung_no_truoc_document_set(self):
        src = _read("approval_center", "shared", "requests", "command_service.py")
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "save_draft"][0]
        body = ast.unparse(fn)
        i = body.index("_blank_attach_would_wipe(document, fieldname, data.get(fieldname))")
        j = body.index("document.set(fieldname, data.get(fieldname))")
        self.assertLess(i, j)


class TestHtml(unittest.TestCase):
    def test_form_sua_lay_detail_moi(self):
        h = _read("approval_center", "features", "payment_request", "ui", "main_section.html")
        i = h.index("function startEditDraft(det)")
        self.assertIn('call("get_detail",{name:name}).then(function(fresh){ _startEditDraftWith(fresh||det); })', h[i:i + 600])
        self.assertIn("function _startEditDraftWith(det)", h)
        self.assertIn('if(state.mode==="create"&&state.id&&state.draft){ call("get_detail"', h)
        self.assertIn("state.draft.request_attachment=v;", h)

    def test_khoi_ky_so_bao_sau_khi_tai(self):
        d = _read("platform", "esign", "ui", "document_signing_section.html")
        self.assertIn("function _announce()", d)
        self.assertEqual(d.count("_announce();"), 3, "ca 3 nhanh sau khi tai xong deu bao")
        self.assertIn("p146_resync_payment_request_sign_wait_expiry", _read("patches.txt"))
        self.assertIn('"function _announce()"', _read("approval_center", "patches", "p146_resync_payment_request_sign_wait_expiry.py"))


if __name__ == "__main__":
    unittest.main()
