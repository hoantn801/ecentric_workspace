# Copyright (c) 2026, eCentric and contributors
"""claim_uploaded_files(): adopt the orphan File row (uploaded without a fieldname) so
Frappe's attach_files_to_document hook does not insert a duplicate row for the Attach field.
Site-free: monkeypatch command_service.frappe."""
import sys
import types
import unittest


def _load():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.session = types.SimpleNamespace(user="u@e.c")
        f.db = types.SimpleNamespace(exists=lambda *a, **k: False, get_value=lambda *a, **k: None,
                                     set_value=lambda *a, **k: None)
        f.logger = lambda *a, **k: types.SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None)
        f.parse_json = lambda x: x
        u = types.ModuleType("frappe.utils"); u.now_datetime = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.requests import command_service as c
    return c


class _Doc:
    def __init__(self, doctype, name, fields, values):
        self.doctype, self.name = doctype, name
        self.meta = types.SimpleNamespace(fields=[types.SimpleNamespace(fieldname=f, fieldtype=t)
                                                  for f, t in fields])
        self._v = values

    def get(self, k):
        return self._v.get(k)


class TestClaimUploadedFiles(unittest.TestCase):
    def setUp(self):
        self.c = _load()
        self._orig = self.c.frappe

    def tearDown(self):
        self.c.frappe = self._orig

    def _stub(self, exists_field_row, orphan_name):
        calls = {"set": []}
        fr = types.ModuleType("frappe")
        fr.db = types.SimpleNamespace(
            exists=lambda dt, filt: exists_field_row,
            get_value=lambda dt, filt, field: orphan_name,
            set_value=lambda dt, name, field, val: calls["set"].append((name, field, val)))
        fr.logger = lambda *a, **k: types.SimpleNamespace(warning=lambda *a, **k: None)
        self.c.frappe = fr
        return calls

    def test_adopts_orphan_row(self):
        calls = self._stub(exists_field_row=False, orphan_name="FILE-1")
        doc = _Doc("EC Asset Request", "EC-ASSR-1",
                   [("request_attachment", "Attach"), ("title", "Data")],
                   {"request_attachment": "/private/files/a.pdf"})
        self.c.claim_uploaded_files(doc)
        self.assertEqual(calls["set"], [("FILE-1", "attached_to_field", "request_attachment")])

    def test_noop_when_already_attached_to_field(self):
        calls = self._stub(exists_field_row=True, orphan_name="FILE-1")
        doc = _Doc("EC Asset Request", "EC-ASSR-1", [("request_attachment", "Attach")],
                   {"request_attachment": "/private/files/a.pdf"})
        self.c.claim_uploaded_files(doc)
        self.assertEqual(calls["set"], [])

    def test_ignores_non_file_values(self):
        calls = self._stub(exists_field_row=False, orphan_name="FILE-1")
        doc = _Doc("EC X", "N1", [("request_attachment", "Attach")],
                   {"request_attachment": "https://example.com/a.pdf"})
        self.c.claim_uploaded_files(doc)
        self.assertEqual(calls["set"], [])

    def test_no_attach_fields(self):
        calls = self._stub(exists_field_row=False, orphan_name=None)
        doc = _Doc("EC Y", "N2", [("title", "Data")], {"title": "x"})
        self.c.claim_uploaded_files(doc)
        self.assertEqual(calls["set"], [])


if __name__ == "__main__":
    unittest.main()
