# Copyright (c) 2026, eCentric and contributors
"""Global Header Standardization contracts.

One canonical header on every migrated route:
- exactly ONE registry-derived breadcrumb container (data-ec-shell-crumbs)
- exactly ONE notification marker (data-ec-notification-bell)
- exactly THREE global header-right slots: Reminder (action-slot), bell,
  Settings (settings-slot) -- Reminder/Settings inert, no fake behavior
- NO Home / Help icons in the global header (they live in the sidebar)
- breadcrumb labels come ONLY from shell.nav (registry parity)
- static markup parity with the JS hydrator (no hydration layout shift)
"""
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))          # .../ecentric_workspace
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.shell import fallback as fb   # noqa: E402
from ecentric_workspace.shell import nav as shell_nav  # noqa: E402


def _read(*parts):
    return io.open(os.path.join(*parts), encoding="utf-8").read()


def _pages():
    return sorted(fb.page_route_map(REPO).items())


class TestCanonicalHeaderPerRoute(unittest.TestCase):

    def test_exactly_one_crumbs_and_one_bell_per_page(self):
        for path, route in _pages():
            src = _read(path)
            self.assertEqual(len(fb.CRUMBS_RE.findall(src)), 1, route)
            self.assertEqual(src.count('data-ec-notification-bell="1"'), 1, route)
            self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1, route)

    def test_three_global_slots_reminder_bell_settings(self):
        for path, route in _pages():
            src = _read(path)
            self.assertEqual(src.count('data-ec-shell-action-slot="1"'), 1, route)
            self.assertEqual(src.count('data-ec-shell-settings-slot="1"'), 1, route)
            tb = fb.TBRIGHT_RE.search(src)
            self.assertIsNotNone(tb, route)
            # order inside header-right: reminder < bell < settings
            inner = tb.group(0)
            self.assertLess(inner.index('data-ec-shell-action-slot="1"'),
                            inner.index('data-ec-notification-bell="1"'), route)
            self.assertLess(inner.index('data-ec-notification-bell="1"'),
                            inner.index('data-ec-shell-settings-slot="1"'), route)

    def test_no_home_or_help_icons_in_global_header(self):
        # structural: the removed legacy elements, in ANY encoding variant
        home = re.compile(r'<(?:a|button)[^>]*class="(?:icon-btn|ec-ib)"[^>]*'
                          r'title="Trang ch(?:ủ|&#7911;)"')
        help_ = re.compile(r'<(?:a|button)[^>]*class="(?:icon-btn|ec-ib)"')
        for path, route in _pages():
            src = _read(path)
            self.assertIsNone(home.search(src), route)
            self.assertIsNone(help_.search(src), route + ": legacy icon-btn/ec-ib remains")
            self.assertNotIn("docs.ecentric.vn", src, route)

    def test_settings_slot_still_inert(self):
        # Phase 1b: the REMINDER slot is now active; the SETTINGS slot stays an
        # inert disabled placeholder (no governed destination yet).
        onclick = re.compile(r'data-ec-shell-settings-slot="1"[^>]*onclick')
        for path, route in _pages():
            src = _read(path)
            self.assertIsNone(onclick.search(src), route)
            for m in re.finditer(r'<button[^>]*data-ec-shell-settings-slot="1"[^>]*>', src):
                self.assertIn("disabled", m.group(0), route)
                self.assertIn('aria-disabled="true"', m.group(0), route)


class TestBreadcrumbRegistryParity(unittest.TestCase):
    """Crumb labels are the registry's labels -- no second route map."""

    def test_crumb_matches_registry_entry(self):
        items = shell_nav.compose()
        flat, pgroup = [], {}
        for it in items:
            flat.append(it)
            for ch in it.get("children") or []:
                flat.append(ch)
                pgroup[ch["key"]] = it.get("group") or ""
        for path, route in _pages():
            src = _read(path)
            inner = fb.CRUMBS_RE.search(src).group(2)
            key = fb.match_active(items, route)
            it = next(x for x in flat if x["key"] == key)
            group = it.get("group") or pgroup.get(it["key"], "")
            self.assertIn(fb._esc(it["label"]), inner, route)
            if group:
                self.assertIn(
                    '<span class="ec-shell-crumb-group">%s</span>' % fb._esc(group),
                    inner, route)
            # exact-route page with no detail => current, never self-link
            if fb._norm(it["route"]) == fb._norm(route) and "crumb-detail" not in inner:
                self.assertNotIn("ec-shell-crumblink", inner, route)
            else:
                self.assertIn('<a class="ec-shell-crumblink" href="%s">' % it["route"],
                              inner, route)

    def test_regeneration_is_idempotent(self):
        # hydration/static parity guard: the committed pages ARE what the
        # canonical renderer produces (no drift, no layout shift on regen)
        changed, _ = fb.regenerate(REPO, check=True)
        self.assertEqual(changed, [], "pages drifted from canonical renderer")

    def test_detail_contract_preserved(self):
        # /approval keeps its live business nodes inside the canonical crumb
        src = _read(APP, "legacy_pages", "approval_page", "main_section.html")
        inner = fb.CRUMBS_RE.search(src).group(2)
        self.assertIn('data-ec-shell-crumb-detail="1"', inner)
        self.assertIn('id="pageTitle"', inner)
        for marker in ('class="back-btn" href="/all-ticket"', 'id="tkId"', 'id="tkStatus"'):
            self.assertIn(marker, src, marker)


class TestHydrationParity(unittest.TestCase):
    """ec_shell.js must emit the SAME header-right markup as the static
    fallback (first paint == hydrated paint => no layout shift)."""

    def test_js_carries_static_tbright_fragments(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        static = fb.render_tbright_inner()
        for frag in ('data-ec-shell-action-slot="1"',                       # reminder (active)
                     'data-ec-shell-reminder-badge="1"',                     # badge node
                     'data-ec-shell-settings-slot="1" disabled aria-disabled="true"',  # settings inert
                     'title="Cài đặt (sắp ra mắt)"',
                     'data-ec-notification-bell="1"'):
            self.assertIn(frag, static, "static: " + frag)
            self.assertIn(frag, js, "js: " + frag)
        # reminder is ACTIVE now: NOT disabled, real title
        self.assertNotIn('data-ec-shell-action-slot="1" disabled', static)
        self.assertIn('title="Nhắc việc"', static)
        self.assertIn('title="Nhắc việc"', js)
        for icon in ("reminder", "gear"):
            self.assertIn(fb.ICONS[icon], js, icon)

    def test_gbsflow_gets_full_canonical_topbar(self):
        src = _read(APP, "legacy_pages", "docs_gbsflow", "main_section.html")
        self.assertEqual(src.count('data-ec-shell-topbar="1"'), 1)
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(".ec-shell-topbar{", css)
        self.assertIn(".ec-shell-crumbs{", css)


class TestHeaderReminder(unittest.TestCase):
    """Phase 1b: Header Reminder slot -- active button + badge + drawer over
    the SHARED action feed. NC bell + Settings contracts preserved."""

    def test_reminder_button_active_with_badge_node(self):
        static = fb.render_tbright_inner()
        js = _read(APP, "public", "js", "ec_shell.js")
        for frag in ('class="ec-shell-iconbtn ec-shell-reminder"',
                     'data-ec-shell-action-slot="1"',
                     'data-ec-shell-reminder-badge="1"',
                     'aria-haspopup="dialog"'):
            self.assertIn(frag, static, "static: " + frag)
            self.assertIn(frag, js, "js: " + frag)
        # badge hidden at SSR (count is client-side, session-scoped)
        self.assertIn('data-ec-shell-reminder-badge="1" hidden', static)

    def test_reminder_delegates_shared_feed_and_caps_badge(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        # header endpoint = get_reminder_summary (delegates build_feed)
        self.assertIn("action_center.api.get_reminder_summary", js)
        # attention badge caps at 9+
        self.assertIn("n > 9 ? '9+'", js)
        self.assertIn("attention_count", js)
        # drawer buckets + total + Xem tất cả
        for frag in ("Quá hạn", "Cần làm", "Sắp tới", "Không hạn",
                     "ec-shell-reminder-drawer", "Xem tất cả", "ec-shell-rm-total"):
            self.assertIn(frag, js, frag)
        # edge states
        self.assertIn("Không tải được", js)               # API error
        self.assertIn("Không có việc nào cần làm", js)     # empty

    def test_nc_and_settings_contracts_preserved(self):
        static = fb.render_tbright_inner()
        self.assertEqual(static.count('data-ec-notification-bell="1"'), 1)
        self.assertIn('href="/app/notification-log"', static)
        self.assertIn('data-ec-shell-settings-slot="1" disabled', static)

    def test_reminder_badge_css_within_z_budget(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(".ec-shell-reminder-badge{", css)
        self.assertIn(".ec-shell-reminder-drawer{", css)
        # drawer z-index must not exceed the NC popover budget (1000)
        import re as _re
        m = _re.search(r"\.ec-shell-reminder-drawer\{[^}]*z-index:(\d+)", css)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 1000)


if __name__ == "__main__":
    unittest.main()
