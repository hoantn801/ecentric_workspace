# Copyright (c) 2026, eCentric and contributors
"""dedupe_attachments(): one row per physical file.

Uploading through a form creates TWO File records for the same upload (upload_file stores
one with attached_to_field empty; Frappe's attach_files_to_document hook, whose duplicate
check includes attached_to_field, then stores a second one for the Attach field). Both
point at the same file_url, so the attachment list showed every file twice."""
import sys
import types
import unittest


def _load():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
        f.get_all = lambda *a, **k: []
        u = types.ModuleType("frappe.utils")
        u.now_datetime = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.requests import query_service as q
    return q


class TestDedupeAttachments(unittest.TestCase):
    def setUp(self):
        self.q = _load()

    def test_collapses_same_file_url_keeping_earliest(self):
        rows = [
            {"file_name": "bao-gia.pdf", "file_url": "/private/files/bao-gia.pdf", "creation": "2026-08-19 15:46:59"},
            {"file_name": "bao-gia.pdf", "file_url": "/private/files/bao-gia.pdf", "creation": "2026-08-19 15:47:51"},
        ]
        out = self.q.dedupe_attachments(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["creation"], "2026-08-19 15:46:59")

    def test_keeps_distinct_files(self):
        rows = [
            {"file_name": "a.pdf", "file_url": "/private/files/a.pdf"},
            {"file_name": "b.pdf", "file_url": "/private/files/b.pdf"},
        ]
        self.assertEqual(len(self.q.dedupe_attachments(rows)), 2)

    def test_missing_url_falls_back_to_name(self):
        rows = [{"file_name": "x.pdf", "file_url": ""}, {"file_name": "x.pdf", "file_url": ""},
                {"file_name": "y.pdf", "file_url": ""}]
        self.assertEqual(len(self.q.dedupe_attachments(rows)), 2)

    def test_empty_and_none(self):
        self.assertEqual(self.q.dedupe_attachments([]), [])
        self.assertEqual(self.q.dedupe_attachments(None), [])


if __name__ == "__main__":
    unittest.main()
