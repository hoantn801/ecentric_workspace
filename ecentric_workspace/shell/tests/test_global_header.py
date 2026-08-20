# Copyright (c) 2026, eCentric and contributors
"""Global Header Standardization contracts.

One canonical header on every migrated route:
- exactly ONE registry-derived breadcrumb container (data-ec-shell-crumbs)
- exactly TWO global header-right slots: "Việc của tôi" inbox (action-slot)
  and Settings (settings-slot) -- Settings inert, no fake behavior
- NO standalone notification bell: notifications moved into the inbox drawer's
  right lane (PO 2026-08-20); notification DELIVERY is unaffected
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
            self.assertEqual(src.count('data-ec-notification-bell="1"'), 0, route)
            self.assertEqual(src.count('data-ec-shell-header-right="1"'), 1, route)

    def test_two_global_slots_inbox_settings(self):
        for path, route in _pages():
            src = _read(path)
            self.assertEqual(src.count('data-ec-shell-action-slot="1"'), 1, route)
            self.assertEqual(src.count('data-ec-shell-settings-slot="1"'), 1, route)
            tb = fb.TBRIGHT_RE.search(src)
            self.assertIsNotNone(tb, route)
            inner = tb.group(0)
            # order inside header-right: inbox < settings, and NO bell survives
            self.assertLess(inner.index('data-ec-shell-action-slot="1"'),
                            inner.index('data-ec-shell-settings-slot="1"'), route)
            self.assertNotIn('data-ec-notification-bell', inner, route)
            self.assertIn('Việc của tôi', inner, route)

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
            it = next((x for x in flat if x["key"] == key), None)
            if it is None:
                # GD2 C2: page retired from the sidebar (create_rec/gbs.po/gbs.so/
                # create_vendor) but kept live. Its route no longer matches a nav
                # entry, so the breadcrumb degrades to detail-only with NO orphaned
                # crumb-link pointing at a removed registry item.
                self.assertNotIn("ec-shell-crumblink", inner, route)
                continue
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
                     'title="Cài đặt (sắp ra mắt)"'):
            self.assertIn(frag, static, "static: " + frag)
            self.assertIn(frag, js, "js: " + frag)
        # the standalone bell is GONE from the header (merged into the inbox)
        self.assertNotIn('data-ec-notification-bell="1"', static)
        # inbox is ACTIVE: NOT disabled, real title
        self.assertNotIn('data-ec-shell-action-slot="1" disabled', static)
        self.assertIn('title="Việc của tôi"', static)
        self.assertIn('title="Việc của tôi"', js)
        for icon in ("inbox", "gear"):
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
        # header endpoints: summary (per-bucket previews) + bucket (Xem thêm)
        self.assertIn("action_center.api.get_reminder_summary", js)
        self.assertIn("action_center.api.get_reminder_bucket", js)
        # attention badge caps at 9+
        self.assertIn("n > 9 ? '9+'", js)
        self.assertIn("attention_count", js)
        # per-bucket drawer: bucket_items/bucket_has_more, all four labels, total.
        # Phase 1b.2: act_now labelled "Đang xử lý"; footer "Xem tất cả" removed.
        for frag in ("Quá hạn", "Đang xử lý", "Sắp tới", "Không hạn",
                     "ec-shell-reminder-drawer", "ec-shell-rm-total",
                     "d.bucket_items", "d.bucket_has_more"):
            self.assertIn(frag, js, frag)
        self.assertNotIn("Xem tất cả", js)                 # footer removed (Phase 2 page deferred)
        # edge states
        self.assertIn("Không tải được", js)               # API error
        self.assertIn("Không có việc nào cần làm", js)     # empty

    def test_bucket_headers_are_accessible_toggles(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        # accessible toggle: <button>, aria-expanded, chevron, per-bucket panel
        self.assertIn('data-ec-shell-rm-toggle', js)
        self.assertIn('aria-expanded', js)
        self.assertIn('ec-shell-rm-chev', js)
        self.assertIn('data-ec-shell-rm-panel', js)
        # native <button> -> Enter/Space fire click; delegation handles toggle
        self.assertIn("data-ec-shell-rm-toggle]", js)
        self.assertIn("function toggleBucket", js)
        # default expand: overdue/act_now true, upcoming/undated false
        self.assertIn("['overdue', 'Quá hạn', 'ec-shell-rm-overdue', true]", js)
        self.assertIn("['upcoming', 'Sắp tới', '', false]", js)
        # empty buckets hidden (count 0 -> skip)
        self.assertIn("if (!c) return;", js)

    def test_per_bucket_load_more(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        # a REAL accessible button (native -> Enter/Space, focusable) per bucket
        self.assertIn('<button type="button" class="ec-shell-rm-more" data-ec-shell-rm-more="', js)
        self.assertIn("function loadMoreBucket", js)
        self.assertIn("Xem thêm ", js)
        # governed per-bucket pagination via the bucket endpoint + cursor
        self.assertIn("_RM_BUCKET_URL", js)
        self.assertIn("'?bucket=' + encodeURIComponent(key)", js)   # per-bucket independence
        self.assertIn("next_cursor", js)
        # delegated handler fires loadMoreBucket and does NOT navigate away
        self.assertIn("t.closest('[data-ec-shell-rm-more]')", js)
        self.assertIn("ev.preventDefault(); loadMoreBucket(", js)
        # updates the remaining count, and removes the control when all loaded
        self.assertIn("btn.textContent = 'Xem thêm '", js)
        self.assertIn("btn.parentNode.removeChild(btn)", js)

    def test_badge_position_and_scroll_contracts(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        # 9+ capsule sits OUTSIDE the icon top-right; button overflow visible
        self.assertIn(".ec-shell-reminder{ position:relative; overflow:visible;", css)
        import re as _re
        m = _re.search(r"\.ec-shell-reminder-badge\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        badge = m.group(1)
        for prop in ("position:absolute", "top:-4px", "right:-6px", "min-width:16px",
                     "height:16px", "font-size:10px", "line-height:16px", "pointer-events:none"):
            self.assertIn(prop, badge, prop)
        # full-height right-edge panel over a backdrop; each lane scrolls itself
        self.assertIn(".ec-shell-rm-backdrop{", css)
        self.assertIn(".ec-shell-rm-lanes{", css)
        self.assertIn(".ec-shell-rm-lane{", css)
        self.assertIn("overflow-y:auto", css)
        self.assertIn("overscroll-behavior:contain", css)

    def test_notifications_moved_into_drawer_settings_still_inert(self):
        static = fb.render_tbright_inner()
        # no standalone bell in the header any more
        self.assertEqual(static.count('data-ec-notification-bell="1"'), 0)
        self.assertIn('data-ec-shell-settings-slot="1" disabled', static)
        # the drawer's notification lane reads the SAME governed NC endpoints
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("notification_center.api.", js)
        self.assertIn("get_notifications", js)
        self.assertIn("mark_all_read", js)
        self.assertIn('data-ec-shell-nc-lane="1"', js)

    def test_reminder_drawer_portaled_above_page(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(".ec-shell-reminder-badge{", css)
        self.assertIn(".ec-shell-reminder-drawer{", css)
        import re as _re
        m = _re.search(r"\.ec-shell-reminder-drawer\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        rule = m.group(1)
        # Portaled to <body> with position:fixed to escape the topbar stacking
        # context (so the lower "Xem thêm" region is not overlapped -> clickable).
        self.assertIn("position:fixed", rule)
        # z-index must sit ABOVE the topbar (<=900) and the NC popover (1100);
        # the drawer and the NC dropdown are mutually exclusive so this is safe.
        z = int(_re.search(r"z-index:(\d+)", rule).group(1))
        self.assertGreaterEqual(z, 1100)
        # right-edge, full-height panel (not a small anchored popover)
        self.assertIn("right:0", rule)
        self.assertIn("bottom:0", rule)
        # JS portals BOTH the backdrop and the drawer to <body>
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("document.body.appendChild(buildReminderDrawer())", js)
        self.assertIn('data-ec-shell-rm-backdrop', js)
        # two lanes, and rows stay LINKS (no action buttons that could misfire)
        self.assertIn("ec-shell-rm-lanes", js)
        self.assertIn("ec-shell-rm-work", js)
        self.assertIn("ec-shell-rm-nc", js)


if __name__ == "__main__":
    unittest.main()
