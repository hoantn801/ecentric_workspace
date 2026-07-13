# Copyright (c) 2026, eCentric and contributors
"""File-level contracts: opt-in marker ONLY on the 4 pilot pages; shell assets
stay scoped + preserve the Notification Center bell contract."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
FRONTEND = os.path.join(APP, "approval_center", "frontend")
PILOT = {
    "approvals.main_section.html",
    "leave.main_section.html",
    "hr_activity.main_section.html",
    "approvals_dashboard.main_section.html",
}
MARKER = 'data-ec-shell="1"'
BELL = 'data-ec-notification-bell="1"'


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TestOptIn(unittest.TestCase):
    def test_marker_exactly_on_pilot_pages(self):
        for fname in sorted(os.listdir(FRONTEND)):
            if not fname.endswith(".html"):
                continue
            n = _read(FRONTEND, fname).count(MARKER)
            if fname in PILOT:
                self.assertEqual(n, 1, "%s must carry exactly one marker" % fname)
            else:
                self.assertEqual(n, 0, "%s must NOT opt in during Phase 1B" % fname)

    def test_pilot_pages_keep_fallback_nav(self):
        for fname in PILOT:
            src = _read(FRONTEND, fname)
            self.assertIn('class="ec-shell-fallback"', src, fname)
            self.assertIn('href="/approvals"', src, fname)

    def test_pilot_pages_lost_embedded_sidebar(self):
        for fname in PILOT:
            self.assertNotIn('<aside class="ec-sidebar">', _read(FRONTEND, fname), fname)

    def test_hr_activity_wrong_active_link_gone(self):
        src = _read(FRONTEND, "hr_activity.main_section.html")
        self.assertNotIn('nav-item active" href="/approvals/outside-work"', src)


class TestShellAssets(unittest.TestCase):
    def test_js_emits_frozen_bell_contract(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn(BELL, js)
        # must not reimplement NC internals
        for forbidden in ("ec-nc-", "mark_read", "get_notifications", "notification_center.api"):
            self.assertNotIn(forbidden, js)

    def test_js_single_global_and_guards(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("window._ecShellV1Installed", js)
        self.assertIn("window.ECShell", js)
        self.assertNotIn("new MutationObserver", js)  # no observer USAGE in v1
        self.assertNotIn("new window.MutationObserver", js)

    def test_css_is_fully_scoped(self):
        css = _read(APP, "public", "css", "ec_shell.css")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for line in css.splitlines():
            s = line.strip()
            if not s or s.startswith("@") or "{" not in s or s.startswith("--"):
                continue
            sel = s.split("{")[0].strip()
            if not sel:
                continue
            for part in sel.split(","):
                part = part.strip()
                if not part:
                    continue
                self.assertTrue(
                    part.startswith(".ec-shell") or part.startswith("[data-ec-shell")
                    or part.startswith("body.ec-shell-noscroll")
                    or part.startswith("@"),
                    "unscoped CSS selector: %r" % part)

    def test_hooks_include_both_assets_and_keep_nc_first(self):
        hooks = _read(APP, "hooks.py")
        self.assertIn('web_include_js = ["notification_center.bundle.js", "ec_shell.bundle.js"]', hooks)
        self.assertIn('web_include_css = ["ec_shell.bundle.css"]', hooks)


if __name__ == "__main__":
    unittest.main()
