# Copyright (c) 2026, eCentric and contributors
"""Deck cua phong ban rieng tu KHONG duoc doi sang link chia se to chuc.

Vi sao rieng mot bo test: link organization-scope mo duoc bang bat ky tai khoan
nao trong tenant va KHONG di qua quyen Frappe. Voi bao cao Management, tao link
do la vuot mat toan bo luat o `permissions.py` -- danh sach an ban ghi, nhung ai
co URL van doc duoc deck. Hai chan nay phai cung ton tai:

  * `_candidates` loc san (khong lam viec thua)
  * `_convert_row` chan ngay truoc khi tao link (khong di vong duoc)

Chan thu hai moi la chan that. Chan thu nhat chi de do tai.

    bench run-tests --module ecentric_workspace.weekly_report.tests.test_deck_sharing_private
"""

import sys
import types
import unittest

if "frappe" not in sys.modules:
    _fr = types.ModuleType("frappe")
    _fr.get_all = lambda *a, **k: []
    _fr.get_roles = lambda u: []
    _fr.whitelist = lambda *a, **k: (lambda f: f)
    _fr._ = lambda s: s
    _fr.PermissionError = type("PermissionError", (Exception,), {})
    _fr.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or Exception)(msg))
    _fr.session = types.SimpleNamespace(user="tester")
    _fr.local = types.SimpleNamespace()
    _fr.db = types.SimpleNamespace(
        get_value=lambda *a, **k: None, sql=lambda *a, **k: [],
        escape=lambda s: "'" + str(s).replace("'", "''") + "'")
    sys.modules["frappe"] = _fr
    _u = types.ModuleType("frappe.utils")
    _u.nowdate = lambda: "2026-09-28"
    _u.add_days = lambda d, n: "2026-09-16"
    sys.modules["frappe.utils"] = _u

import frappe  # noqa: E402

from ecentric_workspace.weekly_report import deck_sharing as DS  # noqa: E402

MGMT = DS.MANAGEMENT_DEPARTMENT


class ConvertRowGuardTest(unittest.TestCase):
    """Chan thu hai: ngay truoc khi tao link."""

    def setUp(self):
        self.created = []
        self.saved = []
        self._orig = DS.sharepoint.create_org_link
        self._rel = DS.sharepoint.rel_path_from_web_url

        class _Doc(object):
            def __init__(inner, name):
                inner.name = name
                inner.slide_deck = ""

            def save(inner, **k):
                self.saved.append((inner.name, inner.slide_deck))
        frappe.get_doc = lambda dt, name: _Doc(name)

        def create(rel_path, token):
            self.created.append(rel_path)
            return "https://x.sharepoint.com/:b:/s/operation/IQfake"
        DS.sharepoint.create_org_link = create
        DS.sharepoint.rel_path_from_web_url = lambda url, dept: "Weekly/a.pdf"

    def tearDown(self):
        DS.sharepoint.create_org_link = self._orig
        DS.sharepoint.rel_path_from_web_url = self._rel

    def _stats(self):
        return {"scanned": 0, "converted": 0, "records": 0, "failed": 0,
                "skipped_private": 0, "errors": []}

    def test_management_row_creates_no_link(self):
        stats = self._stats()
        row = {"name": "WTU-W39-CEO", "department": MGMT,
               "slide_deck": "https://x.sharepoint.com/sites/operation/Shared Documents/a.pdf"}
        changed = DS._convert_row(row, "TOKEN", stats)
        self.assertEqual(changed, 0)
        self.assertEqual(self.created, [],
                         "khong duoc goi Graph tao link cho deck Management")
        self.assertEqual(stats["skipped_private"], 1)

    def test_ordinary_row_still_converts(self):
        """Chan phai hep. Moi phong khac van chuyen binh thuong."""
        stats = self._stats()
        row = {"name": "WTU-W39-NV", "department": "Service - EC",
               "slide_deck": "https://x.sharepoint.com/sites/operation/Shared Documents/a.pdf"}
        changed = DS._convert_row(row, "TOKEN", stats)
        self.assertEqual(changed, 1)
        self.assertEqual(len(self.created), 1)
        self.assertEqual(stats["skipped_private"], 0)

    def test_guard_runs_before_any_graph_call_even_on_many_urls(self):
        """Nhieu deck trong mot ban ghi: khong duoc lot tep nao."""
        stats = self._stats()
        row = {"name": "WTU-W39-CEO", "department": MGMT,
               "slide_deck": "https://x/a.pdf\nhttps://x/b.pdf\nhttps://x/c.pdf"}
        DS._convert_row(row, "TOKEN", stats)
        self.assertEqual(self.created, [])


class CandidateFilterTest(unittest.TestCase):
    """Chan thu nhat: khong keo ban ghi Management ve ngay tu truy van."""

    def test_query_excludes_private_departments(self):
        seen = {}

        def get_all(doctype, **k):
            seen.update(k)
            return []
        orig = frappe.get_all
        frappe.get_all = get_all
        try:
            DS._candidates(None, 25)
        finally:
            frappe.get_all = orig
        self.assertEqual(seen["filters"].get("department"), ["not in", [MGMT]])


class SharedConstantTest(unittest.TestCase):
    def test_private_department_comes_from_permissions_module(self):
        """Mot dinh nghia, mot noi. Neu ten phong ban doi ma hai noi go rieng,
        cai nay im lang hong -- deck lai chia se ra nhu cu."""
        from ecentric_workspace.weekly_report import permissions
        self.assertIn(permissions.MANAGEMENT_DEPARTMENT, DS.PRIVATE_DEPARTMENTS)


if __name__ == "__main__":
    unittest.main()
