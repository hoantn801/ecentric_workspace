# Copyright (c) 2026, eCentric and contributors
"""HR shell-boundary transform regression tests (pure `transform`, no bench).

Covers the 2026-07-21 production regression: /ec-hr/attendance carried ONE
raw "<" text node between <div class="ec-hr-dashwrap"> and the shell mount
(leftover of the original HR aside injection). The transform must remove it
(transform-level fix, not CSS), keep salary untouched, and keep every
boundary/byte contract."""
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

if "frappe" not in sys.modules:
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda f: f)
    stub._ = lambda s: s
    stub.session = types.SimpleNamespace(user="test@example.com")
    sys.modules["frappe"] = stub

from ecentric_workspace.hr.pages import shell_boundary as sb  # noqa: E402
from ecentric_workspace.shell import fallback as fb           # noqa: E402


def _page(stray="", scripts=('<script id="ec-hr-attendance">a()</script>',)):
    return (
        '<!-- HIDE-NAVBAR-V1 --><style>.x{}</style>'
        '<div class="ec-hr-dashwrap">' + stray +
        '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="n">OLD</aside>'
        '<main class="ec-hr-main">'
        '<div class="ec-shell-tbright" data-ec-shell-header-right="1">OLD'
        '<a data-ec-notification-bell="1"></a></div>'
        '<div id="ec-hr-att-root">BUSINESS</div>' + "".join(scripts) +
        '</main></div>'
    )


class TestStrayLiteralRepair(unittest.TestCase):
    def test_attendance_stray_lt_removed(self):
        new, info = sb.transform(_page(stray="<"), "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertEqual(info["stray_removed"], 1)
        self._assert_clean(new)

    def test_entity_variant_removed(self):
        new, info = sb.transform(_page(stray="&lt;"), "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertEqual(info["stray_removed"], 1)
        self._assert_clean(new)

    def test_clean_page_untouched_and_idempotent(self):
        new, info = sb.transform(_page(), "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertEqual(info["stray_removed"], 0)
        again, info2 = sb.transform(new, "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertEqual(again, new, "transform must be idempotent")
        self.assertEqual(info2["stray_removed"], 0)

    def test_salary_page_with_protections_stays_clean(self):
        scripts = ('<script id="ec-salary-noprerender">g()</script>',
                   '<script id="ec-hr-salary">f()</script>')
        src = _page(scripts=scripts).replace("ec-hr-att-root", "ec-hr-sal-root")
        new, info = sb.transform(src, "ec-hr/salary",
                                 ["ec-salary-noprerender", "ec-hr-salary"])
        self.assertEqual(info["stray_removed"], 0)
        self.assertEqual(new.count('id="ec-salary-noprerender"'), 1)
        self.assertEqual(new.count('id="ec-hr-salary"'), 1)
        self._assert_clean(new)

    def test_business_bytes_preserved_outside_zones(self):
        src = _page(stray="<")
        new, _ = sb.transform(src, "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertIn('<div id="ec-hr-att-root">BUSINESS</div>', new)
        self.assertIn("<!-- HIDE-NAVBAR-V1 -->", new)
        # the repaired baseline (stray dropped) must strip-equal the output
        self.assertEqual(sb._strip_zones(sb.STRAY_LT_RE.sub("", src)),
                         sb._strip_zones(new))

    def test_stray_anchor_is_strict(self):
        # a "<" that is NOT immediately before the mount must never be eaten
        src = _page().replace("BUSINESS", "a &lt; b and x < y")
        new, info = sb.transform(src, "ec-hr/attendance", ["ec-hr-attendance"])
        self.assertEqual(info["stray_removed"], 0)
        self.assertIn("a &lt; b and x < y", new)

    def _assert_clean(self, new):
        # zero non-whitespace text before the mount inside the dash wrapper
        m = re.search(r'<div class="ec-hr-dashwrap"[^>]*>(.*?)<aside class="ec-shell-mount"',
                      new, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), "", "stray text before shell mount")
        self.assertIsNone(sb.STRAY_LT_RE.search(new))
        self.assertEqual(new.count('<aside class="ec-shell-mount"'), 1)
        self.assertEqual(new.count('data-ec-shell-topbar="1"'), 1)
        self.assertEqual(new.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(new.count('data-ec-notification-bell="1"'), 1)
        # HR context nav rendered statically
        self.assertIn('<div class="ec-shell-grouplabel">Nhân sự</div>', new)


if __name__ == "__main__":
    unittest.main()
