# Copyright (c) 2026, eCentric and contributors
"""7 trang Dao tao + Quiz: ?v= khop noi dung asset, khong chuoi Jinja, co trong ban ke resync,
route khop nav.

    python -m unittest ecentric_workspace.dao_tao.tests.test_pages
"""
import io
import json
import os
import re
import unittest

from ecentric_workspace.dao_tao.pages import assets

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))


class PagesTest(unittest.TestCase):
    def html(self, key):
        return io.open(assets.page_path(key), encoding="utf-8").read()

    def test_asset_versions_current(self):
        for key in assets.PAGE_KEYS:
            self.assertEqual(assets.stale(self.html(key)), [], key)

    def test_no_jinja_markers(self):
        for key in assets.PAGE_KEYS:
            h = self.html(key)
            for m in ("{{", "}}", "{%", "%}", "{#"):
                self.assertNotIn(m, h, "%s chua %s - Web Page render qua Jinja" % (key, m))

    def test_in_resync_manifest(self):
        man = json.load(io.open(os.path.join(APP, "approval_center", "patches", "resync_manifest.json"), encoding="utf-8"))
        for key in assets.PAGE_KEYS:
            self.assertIn("dao_tao/pages/%s/main_section.html" % key, man)

    def test_scripts_exist(self):
        for key in assets.PAGE_KEYS:
            for src in re.findall(r'src="/assets/ecentric_workspace/([^"?]+)', self.html(key)):
                self.assertTrue(os.path.isfile(os.path.join(APP, "public", src)), src)

    def test_js_has_no_answer_keys_leak_helpers(self):
        """May nguoi choi khong tu cham: JS khong duoc chua ham grade / so dap an."""
        js = io.open(os.path.join(APP, "public", "dao_tao", "ec_dt_quiz_play.js"), encoding="utf-8").read()
        self.assertNotIn("grade(", js)


if __name__ == "__main__":
    unittest.main()
