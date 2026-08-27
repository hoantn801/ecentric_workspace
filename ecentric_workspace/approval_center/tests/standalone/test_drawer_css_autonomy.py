# Copyright (c) 2026, eCentric and contributors
"""The signing drawer must carry its own styling, wherever it ends up in the DOM.

Two failures made this necessary, and the second one was mine.

1. Hoan reported the drawer buttons had "suddenly gone ugly". The drawer asked for the ERP
   shell's CSS variables twenty times (--gray-200, --navy, ...). Those variables live in
   head_html on production and are not in this repo: the drawer does not own them, cannot
   see when they change, and has no say when they do. One redefinition upstream and the
   chrome changes underneath it.

2. Worse, and self-inflicted: the overlay is now moved to <body> so position:fixed is
   measured against the viewport. But 23 rules were written as `.ec-docsign .ecd-x`, and
   `.ec-docsign` is exactly the ancestor being left behind. Shipping the move on its own
   would have stripped the drawer of its styling - a fix that breaks the thing it fixes.

So every scoped rule now also carries a `.ecd-drawer-ov` twin, and colours come from a
palette the drawer declares itself.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _drawer_css():
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, "platform", "esign", "ui", "document_signing_section.html")
        tried.append(path)
        if os.path.exists(path):
            html = io.open(path, encoding="utf-8").read()
            return re.search(r"<style[^>]*>([\s\S]*?)</style>", html).group(1)
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay document_signing_section.html. Da thu:\n  "
                         + "\n  ".join(tried))


def _selectors(css):
    css = re.sub(r"/\*[\s\S]*?\*/", "", css)
    return [s.strip() for block in re.findall(r"([^{}]+)\{", css)
            for s in block.split(",") if s.strip()]


class TestSurvivesThePortal(unittest.TestCase):
    def setUp(self):
        self.css = _drawer_css()
        self.sels = _selectors(self.css)

    def test_every_scoped_rule_has_a_drawer_twin(self):
        orphans = []
        for sel in self.sels:
            if not sel.startswith(".ec-docsign "):
                continue
            twin = ".ecd-drawer-ov " + sel[len(".ec-docsign "):]
            if twin not in self.sels:
                orphans.append(sel)
        self.assertEqual(orphans, [],
                         "cac rule nay se CHET khi lop phu chuyen ra <body>: %s" % orphans[:6])

    def test_there_really_are_scoped_rules_to_protect(self):
        """Neu con so nay ve 0 thi phep kiem tren thanh vo nghia ma van xanh."""
        scoped = [s for s in self.sels if s.startswith(".ec-docsign ")]
        self.assertGreater(len(scoped), 10, "khong con rule nao de bao ve - kiem tra lai")


class TestOwnsItsColours(unittest.TestCase):
    def setUp(self):
        self.css = _drawer_css()

    def test_never_reads_shell_variables(self):
        borrowed = sorted(set(re.findall(r"var\(--(?!ecd-)([a-z0-9-]+)", self.css)))
        self.assertEqual(borrowed, [],
                         "drawer khong duoc phu thuoc bien CSS cua shell: %s" % borrowed)

    def test_declares_its_own_palette_on_both_roots(self):
        block = re.search(r"\.ec-docsign,\s*\.ecd-drawer-ov\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(block, "thieu khoi khai bao bang mau cho ca hai goc")
        for token in ("--ecd-line", "--ecd-ink", "--ecd-brand", "--ecd-dim"):
            self.assertIn(token, block.group(1))

    def test_every_used_variable_is_declared(self):
        block = re.search(r"\.ec-docsign,\s*\.ecd-drawer-ov\s*\{([^}]*)\}", self.css).group(1)
        declared = set(re.findall(r"(--ecd-[a-z0-9-]+)\s*:", block))
        used = set(re.findall(r"var\((--ecd-[a-z0-9-]+)", self.css))
        self.assertEqual(used - declared, set(),
                         "dung bien chua khai bao -> mau roi ve rong: %s" % (used - declared))


if __name__ == "__main__":
    unittest.main()
