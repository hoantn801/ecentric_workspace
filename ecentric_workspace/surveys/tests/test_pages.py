# Copyright (c) 2026, eCentric and contributors
"""4 trang Khao sat + menu: chay khong can bench.

    python -m unittest ecentric_workspace.surveys.tests.test_pages
"""
import io
import os
import re
import unittest

from ecentric_workspace.shell import nav
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.pages import assets

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(os.path.dirname(HERE), "pages")


def html(key):
    return io.open(os.path.join(PAGES, key, "main_section.html"), encoding="utf-8").read()


class TestPages(unittest.TestCase):
    def test_asset_versions_match_files(self):
        for key in assets.PAGE_KEYS:
            with self.subTest(page=key):
                self.assertEqual(assets.stale(html(key)), [],
                                 "?v= lech: chay python -m ecentric_workspace.surveys.pages.assets --stamp")

    def test_every_page_has_shell_root_and_core_first(self):
        for key in assets.PAGE_KEYS:
            with self.subTest(page=key):
                h = html(key)
                self.assertIn('<aside class="ec-shell-mount" data-ec-shell="1"', h)
                self.assertIn('data-page="%s"' % key, h)
                scripts = re.findall(r'surveys/(ec_survey_[a-z]+\.js)\?v=', h)
                self.assertEqual(scripts[0], "ec_survey_core.js", "core phai nap truoc")
                self.assertTrue(all(os.path.isfile(os.path.join(assets.ASSET_DIR, s)) for s in scripts))

    def test_no_jinja_tokens_and_no_inline_business_script(self):
        for key in assets.PAGE_KEYS:
            with self.subTest(page=key):
                h = html(key)
                self.assertNotIn("{{", h)
                self.assertNotIn("{%", h)
                # A65: khong khoi <script> / <style> inline - moi logic nam o asset cua app.
                self.assertNotRegex(h, r"<script(?![^>]*\bsrc=)")
                self.assertNotIn("<style", h)

    def test_routes_match_constants(self):
        routes = []
        for key in ("hub", "fill", "manage", "builder"):
            src = io.open(os.path.join(PAGES, key, "page_sync.py"), encoding="utf-8").read()
            routes.append(re.search(r'ROUTE = "([^"]+)"', src).group(1))
        self.assertEqual(routes, [C.ROUTE_HUB, C.ROUTE_FILL, C.ROUTE_MANAGE, C.ROUTE_BUILDER])


class TestNav(unittest.TestCase):
    def test_routes_resolve_to_surveys_context(self):
        for route in ("/khao-sat", "/khao-sat/lam", "/khao-sat/quan-ly", "/khao-sat/soan"):
            with self.subTest(route=route):
                self.assertEqual(nav.resolve_context(route), "surveys")

    def test_home_has_alias_and_manage_is_role_gated(self):
        home = nav.compose("home")
        self.assertTrue(any(i["route"] == "/khao-sat" for i in home))
        items = {i["key"]: i for i in nav.compose("surveys", roles=[C.ROLE_CREATOR])}
        self.assertIn("surveys.manage", items)
        self.assertNotIn("surveys.manage", {i["key"] for i in nav.compose("surveys", roles=[])})


if __name__ == "__main__":
    unittest.main()
