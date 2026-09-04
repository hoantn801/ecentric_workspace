# Copyright (c) 2026, eCentric and contributors
"""Tab "Cho toi xu ly" kem ban nhap cua toi (05/09, Hoan feedback #1).

1. queries.fetch_my_drafts (code THAT, frappe gia): chi doctype co cot approval_request;
   loc owner=toi, docstatus 0, approval_request chua co; bo Cancelled/Rejected khi co cot
   status; sap xep modified giam dan.
2. api.list_requests chi gan drafts cho box=fulfil trang dau (AST).
3. hub HTML: draftsHtml chi tab fulfil trang dau; nhan "Luu nhap"; nut Tiep tuc.
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


def _read(*p):
    with io.open(os.path.join(_AC, *p), encoding="utf-8") as fh:
        return fh.read()


def _queries(columns, rows):
    fk = types.ModuleType("frappe")
    fk.calls = []

    class _DB(object):
        def table_exists(self, dt):
            return dt in columns

        def has_column(self, dt, col):
            return col in columns.get(dt, ())
    fk.db = _DB()

    def get_all(dt, filters=None, fields=None, order_by=None, limit_page_length=None):
        fk.calls.append((dt, dict(filters)))
        return [types.SimpleNamespace(**r) for r in rows.get(dt, [])]
    fk.get_all = get_all
    D = types.SimpleNamespace
    reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
    reg.BUSINESS_DOCTYPE_DEFINITIONS = {
        "EC Payment Request": D(code="PAYMENT_REQUEST"),
        "EC Leave Request": D(code="LEAVE"),
        "EC Old Thing": D(code="OLD")}
    scope = types.ModuleType("ecentric_workspace.approval_center.reporting.scope")
    mods = {"frappe": fk, "ecentric_workspace.approval_center.shared.registry": reg,
            "ecentric_workspace.approval_center.reporting.scope": scope}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_queries_under_test")
        exec(compile(_read("reporting", "queries.py"), "queries.py", "exec"), m.__dict__)
        out = m.fetch_my_drafts("hien.nguyen@ecentric.vn")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return out, fk.calls


class TestFetchMyDrafts(unittest.TestCase):
    COLS = {"EC Payment Request": ("approval_request", "status"),
            "EC Leave Request": ("approval_request",),
            "EC Old Thing": ("name",)}          # khong co approval_request -> bo qua

    def test_loc_dung_va_bo_doctype_khong_co_cot(self):
        rows = {"EC Payment Request": [{"name": "PR-2", "modified": "2026-09-05 02:00:00", "creation": "x"},
                                       {"name": "PR-1", "modified": "2026-09-04 02:00:00", "creation": "x"}],
                "EC Leave Request": [{"name": "LV-1", "modified": "2026-09-05 01:00:00", "creation": "x"}]}
        out, calls = _queries(self.COLS, rows)
        self.assertEqual([c[0] for c in calls], ["EC Payment Request", "EC Leave Request"])
        f = calls[0][1]
        self.assertEqual(f["owner"], "hien.nguyen@ecentric.vn")
        self.assertEqual(f["docstatus"], 0)
        self.assertEqual(f["approval_request"], ["is", "not set"])
        self.assertEqual(f["status"], ["not in", ["Cancelled", "Rejected"]])
        self.assertNotIn("status", calls[1][1], "doctype khong co cot status thi khong loc status")
        self.assertEqual([r["name"] for r in out], ["PR-2", "LV-1", "PR-1"], "modified giam dan")
        self.assertEqual(out[0]["approval_type"], "PAYMENT_REQUEST")


class TestApiAndHtml(unittest.TestCase):
    def test_api_chi_gan_drafts_cho_fulfil_trang_dau(self):
        fn = [n for n in ast.walk(ast.parse(_read("reporting", "api.py")))
              if isinstance(n, ast.FunctionDef) and n.name == "list_requests"][0]
        src = ast.unparse(fn)
        self.assertIn("if box == 'fulfil' and start == 0:", src)
        self.assertIn("out['drafts'] = _service.my_drafts()", src)

    def test_service_my_drafts_gan_tieu_de_va_route(self):
        fn = [n for n in ast.walk(ast.parse(_read("reporting", "service.py")))
              if isinstance(n, ast.FunctionDef) and n.name == "my_drafts"][0]
        src = ast.unparse(fn)
        self.assertIn("fetch_my_drafts(frappe.session.user)", src)
        self.assertIn("'?id=' + r['name']", src)
        self.assertIn("r['status_label'] = 'Nháp'", src)

    def test_hub_dai_nhap(self):
        h = _read("ui", "all_requests", "main_section.html")
        self.assertIn("function draftsHtml()", h)
        self.assertIn('if(state.box!=="fulfil"||state.start>0||!ds.length) return "";', h)
        self.assertIn('<span class="pill">Lưu nháp</span>', h)
        self.assertIn("state.drafts=(res&&res.drafts)||[]", h)
        self.assertEqual(h.count("innerHTML=drafts+"), 2, "ca luc co dong lan khong co dong")


if __name__ == "__main__":
    unittest.main()
