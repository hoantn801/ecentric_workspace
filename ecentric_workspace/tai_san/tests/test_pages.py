# Copyright (c) 2026, eCentric and contributors
"""6 trang Quan ly tai san: ?v= khop noi dung asset, khong chuoi Jinja, co vo shell, page_sync khop
constants, JS dung ES5, CSS bo hep trong #ec-ts, moi ham API JS goi deu co trong controllers/api.py.

    python -m unittest ecentric_workspace.tai_san.tests.test_pages
(Khong can frappe: doc file bang regex.)
"""
import io
import os
import re
import unittest

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san.pages import assets

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
PUBLIC = os.path.join(assets.PUBLIC_DIR, "tai_san")
EXPECT = {"home": C.ROUTE_HOME, "list": C.ROUTE_LIST, "moves": C.ROUTE_MOVES,
          "repairs": C.ROUTE_REPAIRS, "count": C.ROUTE_COUNT, "mine": C.ROUTE_MINE}


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _js_files():
    return sorted(f for f in os.listdir(PUBLIC) if f.endswith(".js"))


def _strip_js_comments(src):
    # bo comment dong // va /* */ (khong dung trong chuoi cua cac file nay o dau dong)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"^\s*//.*$", "", line) for line in src.splitlines())


def _split_top(head):
    """Tach danh sach selector theo dau phay o muc ngoai cung (bo qua dau phay trong ngoac)."""
    parts, depth, cur = [], 0, ""
    for ch in head:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _css_selectors(css):
    """Tra ve danh sach selector cua moi rule (ke ca trong @media), bo khoi frappe-chrome va @keyframes."""
    css = re.sub(r"/\* frappe-chrome \*/.*?/\* end frappe-chrome \*/", "", css, flags=re.S)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, n = [], 0, len(css)

    def block_end(j):
        depth = 0
        while j < n:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        return n

    def walk(start, stop):
        j = start
        while j < stop:
            k = css.find("{", j, stop)
            if k < 0:
                return
            head = css[j:k].strip()
            end = block_end(k)
            if head.startswith("@keyframes") or head.startswith("@font-face"):
                pass
            elif head.startswith("@"):
                walk(k + 1, end)
            elif head:
                out.extend(s.strip() for s in _split_top(head) if s.strip())
            j = end + 1

    walk(i, n)
    return out


class PagesTest(unittest.TestCase):
    def html(self, key):
        return _read(assets.page_path(key))

    def test_page_keys(self):
        self.assertEqual(set(assets.PAGE_KEYS), set(EXPECT))

    def test_asset_versions_current(self):
        for key in assets.PAGE_KEYS:
            h = self.html(key)
            self.assertEqual(assets.stale(h), [], key)
            self.assertIn("/assets/ecentric_workspace/tai_san/ec_ts.css?v=", h, key)
            self.assertIn("/assets/ecentric_workspace/tai_san/ec_ts_core.js?v=", h, key)
            for ref in re.findall(r'/assets/ecentric_workspace/tai_san/[^"?]+\?v=([0-9a-f]*)', h):
                self.assertEqual(len(ref), 10, key)

    def test_scripts_exist(self):
        for key in assets.PAGE_KEYS:
            for src in re.findall(r'(?:src|href)="/assets/ecentric_workspace/([^"?]+)', self.html(key)):
                self.assertTrue(os.path.isfile(os.path.join(assets.PUBLIC_DIR, src)), "%s: %s" % (key, src))

    def test_no_jinja_markers(self):
        for key in assets.PAGE_KEYS:
            h = self.html(key)
            for m in ("{{", "}}", "{%", "%}", "{#"):
                self.assertNotIn(m, h, "%s chua %s - Web Page render qua Jinja" % (key, m))

    def test_no_inline_script_or_style(self):
        for key in assets.PAGE_KEYS:
            h = self.html(key)
            self.assertNotRegex(h, r"<script(?![^>]*\bsrc=)[^>]*>", key)
            self.assertNotIn("<style", h, key)

    def test_shell_mount_present(self):
        for key in assets.PAGE_KEYS:
            h = self.html(key)
            self.assertIn('<aside class="ec-shell-mount" data-ec-shell="1"', h, key)
            self.assertIn('data-ec-shell-topbar="1"', h, key)
            self.assertIn('data-ec-shell-crumbs="1"', h, key)
            self.assertIn('data-ec-shell-header-right="1"', h, key)
            self.assertIn("ec-shell-nav", h, "%s: vung shell chua sinh" % key)
            self.assertIn('id="ec-ts"', h, key)
            self.assertIn('id="ts-root" data-page="%s"' % key, h, key)

    def test_page_sync_matches_constants(self):
        for key, route in EXPECT.items():
            src = _read(os.path.join(MOD, "pages", key, "page_sync.py"))
            self.assertEqual(re.search(r'^ROUTE = "([^"]+)"', src, re.M).group(1), route, key)
            name = re.search(r'^NAME = "([^"]+)"', src, re.M).group(1)
            title = re.search(r'^TITLE = "([^"]+)"', src, re.M).group(1)
            self.assertTrue(name.startswith("tài-sản"), key)
            self.assertNotIn(" ", name, key)
            self.assertTrue(title.strip(), key)
        names = [re.search(r'^NAME = "([^"]+)"', _read(os.path.join(MOD, "pages", k, "page_sync.py")), re.M).group(1)
                 for k in EXPECT]
        self.assertEqual(len(names), len(set(names)))

    def test_js_is_es5(self):
        for f in _js_files():
            src = _strip_js_comments(_read(os.path.join(PUBLIC, f)))
            self.assertNotIn("=>", src, f)
            self.assertNotIn("`", src, f)
            self.assertIsNone(re.search(r"(^|[^\w.$])(const|let|class)\s+[A-Za-z_$]", src), f)

    def test_css_scoped(self):
        css = _read(os.path.join(PUBLIC, "ec_ts.css"))
        self.assertNotIn(":root", css)
        sels = _css_selectors(css)
        self.assertTrue(len(sels) > 50)
        for s in sels:
            self.assertTrue(s.startswith("#ec-ts"), "selector khong bo trong #ec-ts: %s" % s)

    def test_api_methods_exist(self):
        api = _read(os.path.join(MOD, "controllers", "api.py"))
        defined = set(re.findall(r"^def ([a-z][a-z_]*)\(", api, re.M))
        called = set()
        for f in _js_files():
            src = _read(os.path.join(PUBLIC, f))
            called.update(re.findall(r'\b(?:get|post)\("([a-z_]+)"', src))
        self.assertTrue(called)
        self.assertEqual(sorted(called - defined), [])


if __name__ == "__main__":
    unittest.main()
