# Copyright (c) 2026, eCentric and contributors
"""Deck-path and submit-validation tests.

These run WITHOUT bench on purpose: they cover the pure logic that the
python3.14 sandbox incident made expensive to get wrong (path building, URL
parsing, payload validation). The bench-level happy path for submit_service.submit
is tracked separately -- see the note at the bottom of this file.
"""

import unittest

from ecentric_workspace.weekly_report import sharepoint, submit_service


class _FakeDoc(object):
    def __init__(self, slide_deck=""):
        self.slide_deck = slide_deck


class TestDeckPath(unittest.TestCase):
    def test_build_deck_path(self):
        self.assertEqual(
            sharepoint.build_deck_path("2026-W38", "NV00001", "Management", "a.pdf"),
            "Weekly Reports/Management/2026-W38_NV00001_a.pdf",
        )

    def test_build_deck_path_strips_separators(self):
        got = sharepoint.build_deck_path("2026-W38", "NV1", "Media", "../../evil.pdf")
        self.assertNotIn("..", got.rsplit("/", 1)[-1].replace("evil", ""))
        self.assertTrue(got.startswith("Weekly Reports/Media/"))

    def test_build_deck_path_defaults_department(self):
        got = sharepoint.build_deck_path("2026-W38", "NV1", "", "a.pdf")
        self.assertEqual(got, "Weekly Reports/Unknown/2026-W38_NV1_a.pdf")

    def test_rel_path_from_direct_web_url(self):
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/"
            "Shared%20Documents/Weekly%20Reports/Media/2026-W38_NV1_a.pdf"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url),
            "Weekly Reports/Media/2026-W38_NV1_a.pdf",
        )

    def test_rel_path_drops_query_and_fragment(self):
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/"
            "Shared%20Documents/Weekly%20Reports/Media/a.pdf?web=1#a.pdf"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url), "Weekly Reports/Media/a.pdf"
        )

    def test_rel_path_unparseable_returns_empty(self):
        # Organisation share links carry no path -- must not be guessed at.
        self.assertEqual(
            sharepoint.rel_path_from_web_url(
                "https://boxmeglobal.sharepoint.com/:b:/s/operation/IQAX123"
            ),
            "",
        )


class TestSubmitValidation(unittest.TestCase):
    def test_missing_week_label_raises(self):
        with self.assertRaises(submit_service.SubmitError):
            submit_service.submit({"employee": "HR-EMP-00001"})

    def test_missing_employee_raises(self):
        with self.assertRaises(submit_service.SubmitError):
            submit_service.submit({"week_label": "2026-W38"})

    def test_blank_values_raise(self):
        with self.assertRaises(submit_service.SubmitError):
            submit_service.submit({"week_label": "  ", "employee": "  "})


class TestDeckListParsing(unittest.TestCase):
    def test_plain_newline_list(self):
        doc = _FakeDoc("http://a/1.pdf\nhttp://a/2.pdf")
        self.assertEqual(
            submit_service._current_urls(doc), ["http://a/1.pdf", "http://a/2.pdf"]
        )

    def test_legacy_json_blob(self):
        doc = _FakeDoc('["http://a/1.pdf", "http://a/2.pdf"]')
        self.assertEqual(
            submit_service._current_urls(doc), ["http://a/1.pdf", "http://a/2.pdf"]
        )

    def test_empty(self):
        self.assertEqual(submit_service._current_urls(_FakeDoc("")), [])

    def test_dept_clean_strips_abbr(self):
        self.assertEqual(submit_service._dept_clean("Management - EC"), "Management")
        self.assertEqual(submit_service._dept_clean("Media"), "Media")
        self.assertEqual(submit_service._dept_clean(""), "Unknown")


# OWED: a FrappeTestCase happy path asserting submit() creates the WTU with
# status=Submitted and slide_deck set. Deliberately not guessed here -- the
# Weekly Team Update DocType's mandatory fields have not been read, and a test
# written blind would red the QC gate on first bench run rather than catch a
# real defect. Add it once the schema is in front of us.
