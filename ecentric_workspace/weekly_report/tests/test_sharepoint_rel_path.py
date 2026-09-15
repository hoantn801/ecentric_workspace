# Copyright (c) 2026, eCentric and contributors
"""rel_path_from_web_url must understand all THREE deck URL shapes.

Written after 15/09, when shape 3 (organisation share link) was unhandled and
every Gemini re-upload therefore failed. The failure was invisible: the caller
only recorded thrown exceptions, and this path returns "" instead of raising.

The rule had been implemented twice -- here and in gemini_api -- and only one
copy learned about shape 3. gemini_api._extract_rel_path now delegates here, so
these cases cover both callers. If you add a fourth shape, add it here first.
"""

from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import sharepoint

DEPT = "E-commerce Operation - EC"
ROOT = "Weekly Reports/E-commerce Operation/"


class TestRelPathFromWebUrl(FrappeTestCase):
    def test_direct_path_pdf(self):
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/Shared%20Documents/"
            "Weekly%20Reports/E-commerce%20Operation/2026-W38_E1_Bao%20cao.pdf"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url, DEPT),
            ROOT + "2026-W38_E1_Bao cao.pdf",
        )

    def test_office_viewer_url(self):
        url = (
            "https://boxmeglobal.sharepoint.com/sites/operation/_layouts/15/Doc.aspx"
            "?sourcedoc=%7BGUID%7D&file=2026-W37_E1_Bao%20cao.pptx&action=edit"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url, DEPT),
            ROOT + "2026-W37_E1_Bao cao.pptx",
        )

    def test_org_share_link(self):
        """The shape auto_convert_slides_org rewrites every deck into."""
        url = (
            "https://boxmeglobal.sharepoint.com/:b:/s/operation/"
            "IQxYzAbC123#2026-W36_E2_Bao%20cao%20tuan.pdf"
        )
        self.assertEqual(
            sharepoint.rel_path_from_web_url(url, DEPT),
            ROOT + "2026-W36_E2_Bao cao tuan.pdf",
        )

    def test_org_share_without_department_refuses(self):
        """No folder to rebuild the path from -> "" beats a confident wrong path."""
        url = "https://boxmeglobal.sharepoint.com/:b:/s/operation/IQxYz#a.pdf"
        self.assertEqual(sharepoint.rel_path_from_web_url(url, ""), "")

    def test_org_share_without_fragment_refuses(self):
        """create_org_link appends '#<filename>'. Without it we cannot know the
        name, and guessing would address the wrong item."""
        url = "https://boxmeglobal.sharepoint.com/:b:/s/operation/IQxYz"
        self.assertEqual(sharepoint.rel_path_from_web_url(url, DEPT), "")

    def test_unknown_url_refuses(self):
        self.assertEqual(
            sharepoint.rel_path_from_web_url("https://example.com/nope", DEPT), ""
        )

    def test_is_share_url(self):
        self.assertTrue(sharepoint.is_share_url("https://x/:b:/s/operation/IQ"))
        self.assertTrue(sharepoint.is_share_url("https://x/:p:/s/operation/IQ"))
        self.assertFalse(
            sharepoint.is_share_url(
                "https://x/sites/operation/Shared Documents/a.pdf"
            )
        )
        self.assertFalse(sharepoint.is_share_url(""))
