"""Kiem tra transform thuan cua tab_bar mo rong, KHONG can bench."""
import os
import sys, types, io, re, unittest
fake = types.ModuleType("frappe")
fake.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
fake.get_doc = lambda *a, **k: None
fake.get_roles = lambda u: []
fake.throw = lambda *a, **k: (_ for _ in ()).throw(Exception("throw"))
fake.whitelist = lambda **k: (lambda f: f)
fake._ = lambda s: s
sys.modules["frappe"] = fake
frappe_mod = types.ModuleType("frappe")
sys.modules["frappe"]._ = lambda s: s
import importlib.util
spec = importlib.util.spec_from_file_location("tb", os.path.join(os.path.dirname(__file__), "..", "pages", "tab_bar.py"))
tb = importlib.util.module_from_spec(spec)
sys.modules["tb"] = tb
spec.loader.exec_module(tb)

SRC = ('<style>x{y:1}\n' + tb.CSS_ANCHOR + '\n' + tb.MQ_ANCHOR
       + ' #ec-hr-sal-root{padding-bottom:104px} .a{b:1} @media (min-width:1px){.c{d:2}} }\n</style>\n'
       + tb.HTML_OPEN + '<nav>' + tb.MYWORK_A + 'x</a></nav><div class="ec-fabwrap">'
       + '<span class="ec-fablbl">Cham cong</span></div></div>\n'
       + tb.JS_OPEN + 'var a=1;' + tb.JS_CLOSE + '\n')

class T(unittest.TestCase):
    def test_css_brace_matched_not_truncated(self):
        css = tb._css_block(SRC)
        self.assertTrue(css.startswith(tb.CSS_ANCHOR))
        self.assertIn("min-width:1px", css)          # khoi long nhau khong bi cat
        self.assertTrue(css.rstrip().endswith("}"))

    def test_html_and_js_blocks(self):
        self.assertTrue(tb._html_block(SRC).startswith(tb.HTML_OPEN))
        self.assertTrue(tb._html_block(SRC).endswith(tb.HTML_CLOSE))
        self.assertTrue(tb._js_block(SRC).endswith(tb.JS_CLOSE))

    def test_active_hook_added_once_and_idempotent(self):
        once = tb._with_active_hook(SRC)
        self.assertIn('data-p="/viec-cua-toi"', once)
        self.assertEqual(once.count('data-p="/viec-cua-toi"'), 1)
        self.assertEqual(tb._with_active_hook(once), once)

    def test_insert_refuses_a_second_bar(self):
        tb.extract_bar = lambda: ("css #ec-hr-sal-root{}", "<html>", "<js>")
        with self.assertRaises(ValueError):
            tb.insert_transform(SRC, "viec-cua-toi", "#ec-mywork-root")

    def test_insert_is_idempotent(self):
        tb.extract_bar = lambda: (tb.CSS_ANCHOR + " " + tb.SOURCE_ROOT + "{a:1}",
                                  tb.HTML_OPEN + "x" + tb.HTML_CLOSE,
                                  tb.JS_OPEN + "y" + tb.JS_CLOSE)
        out = tb.insert_transform("<main>trang</main>", "viec-cua-toi", "#ec-mywork-root")
        self.assertIn(tb.BAR_MARKER, out)
        self.assertNotIn(tb.SOURCE_ROOT, out)        # da tro dung root cua trang
        self.assertIn("#ec-mywork-root", out)
        self.assertEqual(tb.insert_transform(out, "viec-cua-toi", "#ec-mywork-root"), out)

    def test_active_hook_noop_when_no_tab(self):
        self.assertEqual(tb.active_hook_transform("<p>khong co tab</p>", "x"),
                         "<p>khong co tab</p>")

if __name__ == "__main__":
    unittest.main(verbosity=1)
