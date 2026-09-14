# Copyright (c) 2026, eCentric and contributors
"""Deck-path and submit-validation tests.

These run WITHOUT bench on purpose: they cover the pure logic that the
python3.14 sandbox incident made expensive to get wrong (path building, URL
parsing, payload validation). The bench-level happy path for submit_service.submit
is tracked separately -- see the note at the bottom of this file.
"""

import unittest

from ecentric_workspace.weekly_report import deck_sharing, sharepoint, submit_service


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
        self.assertNotIn("/", got.rsplit("/", 1)[-1])
        self.assertTrue(got.startswith("Weekly Reports/Media/"))

    def test_colon_in_filename_is_removed(self):
        # "Bao cao tuan 11:9.pdf" broke Graph's root:/{path}:/{action} syntax
        # and returned 500 for one submitter.
        got = sharepoint.build_deck_path(
            "2026-W37", "NV1", "Production", "Bao cao tuan 11:9.pdf"
        )
        self.assertNotIn(":", got)
        self.assertEqual(got, "Weekly Reports/Production/2026-W37_NV1_Bao cao tuan 11_9.pdf")

    def test_safe_filename_covers_sharepoint_illegal_set(self):
        self.assertEqual(sharepoint.safe_filename('a"*:<>?|b.pdf'), "a_______b.pdf")
        self.assertEqual(sharepoint.safe_filename("a#b%c.pdf"), "a_b_c.pdf")

    def test_safe_filename_strips_trailing_space_and_dot(self):
        # SharePoint silently rejects these -- the GBS _pending 403 had a name
        # ending in a space.
        self.assertEqual(sharepoint.safe_filename("BAO GIA VOT MUOI .pdf"), "BAO GIA VOT MUOI .pdf")
        self.assertEqual(sharepoint.safe_filename("report.  "), "report")
        self.assertEqual(sharepoint.safe_filename("   "), "deck.pdf")

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

    def test_rel_path_from_office_layouts_url(self):
        # Office decks come back as the viewer URL, which has no folder in it.
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/_layouts/15/"
            "Doc.aspx?sourcedoc=%7BC5461EB7%7D&file=2026-W37_NV00107_Road%20Map.pptx"
            "&action=edit&mobileredirect=true"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url, "Operation & Data & System - EC"),
            "Weekly Reports/Operation & Data & System/2026-W37_NV00107_Road Map.pptx",
        )

    def test_layouts_url_without_department_refuses_to_guess(self):
        # Guessing the folder would make callers delete/re-share the wrong item.
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/_layouts/15/"
            "Doc.aspx?sourcedoc=%7BC5461EB7%7D&file=a.pptx&action=edit"
        )
        self.assertEqual(sharepoint.rel_path_from_web_url(url), "")


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
        self.assertEqual(sharepoint.dept_clean("Management - EC"), "Management")
        self.assertEqual(sharepoint.dept_clean("Media"), "Media")
        self.assertEqual(sharepoint.dept_clean(""), "Unknown")
        # A department containing " - " keeps everything before the last one.
        self.assertEqual(
            sharepoint.dept_clean("Merchandise, Content & Design - EC"),
            "Merchandise, Content & Design",
        )


class TestDeckSharing(unittest.TestCase):
    def test_org_link_detected(self):
        self.assertTrue(
            deck_sharing._is_org_link(
                "https://boxmeglobal.sharepoint.com/:b:/s/operation/IQAX1#a.pdf"
            )
        )

    def test_direct_and_layouts_are_not_org_links(self):
        # Both still need converting -- this is the bug that left 43 .pptx
        # decks unshared: the old filter only looked for the direct shape.
        self.assertFalse(
            deck_sharing._is_org_link(
                "https://x/sites/operation/Shared%20Documents/Weekly%20Reports/M/a.pdf"
            )
        )
        self.assertFalse(
            deck_sharing._is_org_link(
                "https://x/sites/operation/_layouts/15/Doc.aspx?sourcedoc=%7BG%7D&file=a.pptx"
            )
        )

    def test_display_name_escapes(self):
        self.assertEqual(
            deck_sharing._display_name("Weekly Reports/Media/2026-W37_NV1_a.pdf"),
            "2026-W37_NV1_a.pdf",
        )
        self.assertEqual(
            deck_sharing._display_name("Weekly Reports/Media/100%25 done#x.pdf"),
            "100%2525 done%23x.pdf",
        )


# OWED: a FrappeTestCase happy path asserting submit() creates the WTU with
# status=Submitted and slide_deck set. Deliberately not guessed here -- the
# Weekly Team Update DocType's mandatory fields have not been read, and a test
# written blind would red the QC gate on first bench run rather than catch a
# real defect. Add it once the schema is in front of us.
