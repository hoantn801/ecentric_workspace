# Copyright (c) 2026, eCentric and contributors
"""Trang /kalodata: asset ?v= khop noi dung, khong co chuoi Jinja, vo shell sinh dung, co tren menu.

    python -m unittest ecentric_workspace.shared_tools.tests.test_page
"""
import io
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from ecentric_workspace.shared_tools.pages import assets  # noqa: E402

PAGE = assets.page_path("kalodata")


def _html():
    with io.open(PAGE, encoding="utf-8") as fh:
        return fh.read()


class PageTest(unittest.TestCase):
    def test_assets_stamped(self):
        self.assertEqual(assets.stale(_html()), [])

    def test_no_jinja_tokens(self):
        html = _html()
        for tok in ("{{", "}}", "{%", "%}", "{#", "#}"):
            self.assertNotIn(tok, html)

    def test_shell_fallback_in_sync(self):
        from ecentric_workspace.shell import fallback
        self.assertEqual(fallback.page_route_map(ROOT).get(PAGE), "/kalodata")
        changed, _ = fallback.regenerate(ROOT, check=True)
        self.assertNotIn(PAGE, changed)

    def test_menu_has_kalodata(self):
        from ecentric_workspace.shell import nav
        keys = [i["key"] for i in nav.compose("shared_tools")]
        self.assertIn("shared_tools.kalodata", keys)
        company = str(nav.RAIL_LAYOUTS["company"])
        self.assertIn("shared_tools.kalodata", company)

    def test_js_has_no_secret_or_link_logging(self):
        js = io.open(os.path.join(assets.PUBLIC_DIR, "shared_tools", "ec_st_kalodata.js"), encoding="utf-8").read()
        self.assertNotIn("console.log", js)
        self.assertNotIn("localStorage", js)


if __name__ == "__main__":
    unittest.main()
