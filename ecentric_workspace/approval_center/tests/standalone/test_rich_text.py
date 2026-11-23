# Copyright (c) 2026, eCentric and contributors
"""shared/rich_text.py - lop loc cuoi o server cho noi dung soan kieu mail (23/11/2026) va
EC Adhoc Approval Request.validate suy ra `content` tu `content_html`. Khong can site: frappe gia
(sanitize_html khong co -> chi con lop regex, phai tu chan duoc cac mau nguy hiem).
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_rich_text.py
"""
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))
if "frappe" not in sys.modules:
    fk = types.ModuleType("frappe")
    fk.model = types.ModuleType("frappe.model")
    fk.model.document = types.ModuleType("frappe.model.document")
    fk.model.document.Document = type("Document", (object,), {"get": lambda self, k, d=None: getattr(self, k, d)})
    sys.modules.update({"frappe": fk, "frappe.model": fk.model, "frappe.model.document": fk.model.document})

from ecentric_workspace.approval_center.shared import rich_text as RT  # noqa: E402


class SafeHtml(unittest.TestCase):
    def test_strips_dangerous(self):
        h = RT.safe_html('<p onclick="x()">a</p><script>alert(1)</script><img src=x onerror=y>'
                         '<iframe src="//e"></iframe><a href="javascript:alert(1)">l</a><style>b{}</style>')
        for bad in ("onclick", "<script", "onerror", "<img", "<iframe", "javascript:", "<style"):
            self.assertNotIn(bad, h.lower())
        self.assertIn("<p>a</p>", h)

    def test_keeps_format(self):
        h = RT.safe_html('<p><strong>b</strong> <span style="color:red;">r</span></p><table><tr><td>1</td></tr></table>')
        self.assertIn("<strong>b</strong>", h)
        self.assertIn("<table>", h)

    def test_to_text(self):
        self.assertEqual(RT.to_text("<p>Dòng&nbsp;1</p><ul><li>a</li><li>b</li></ul><p>x &amp; y</p>"),
                         "Dòng 1\na\nb\nx & y")
        self.assertEqual(RT.to_text("<p><br></p>"), "")


class AdhocValidate(unittest.TestCase):
    def test_validate_derives_plain_and_sanitizes(self):
        from ecentric_workspace.approval_center.doctype.ec_adhoc_approval_request import ec_adhoc_approval_request as M
        d = M.ECAdhocApprovalRequest()
        d.content_html = '<p>Xin <b>duyệt</b></p><script>x</script>'
        d.content = "cu"
        d.validate()
        self.assertNotIn("script", d.content_html)
        self.assertEqual(d.content, "Xin duyệt")

    def test_validate_keeps_legacy_plain(self):
        from ecentric_workspace.approval_center.doctype.ec_adhoc_approval_request import ec_adhoc_approval_request as M
        d = M.ECAdhocApprovalRequest()
        d.content_html = None
        d.content = "phieu cu"
        d.validate()
        self.assertEqual(d.content, "phieu cu")


if __name__ == "__main__":
    unittest.main()
