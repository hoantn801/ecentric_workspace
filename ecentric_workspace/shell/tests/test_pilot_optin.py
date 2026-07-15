# Copyright (c) 2026, eCentric and contributors
"""File-level contracts: opt-in marker ONLY on the 4 pilot pages; shell assets
stay scoped + preserve the Notification Center bell contract."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
FRONTEND = os.path.join(APP, "approval_center", "frontend")
# All migrated (shell-opted-in) pages: 1B pilots + 1C-alpha Batch A.
PILOT = {
    "approvals.main_section.html",
    "leave.main_section.html",
    "hr_activity.main_section.html",
    "approvals_dashboard.main_section.html",
    "lateral_move.main_section.html",
    "promotion.main_section.html",
    "employee_referral.main_section.html",
    "service_referral.main_section.html",
    "livestream_supplies.main_section.html",
    "livestream_sample.main_section.html",
    # 1C standard rollout (16):
    "affiliate_bonus.main_section.html",
    "asset_damage_loss.main_section.html",
    "asset_request.main_section.html",
    "budget_setting.main_section.html",
    "compensation_leave.main_section.html",
    "daily_target.main_section.html",
    "data_request.main_section.html",
    "document_request.main_section.html",
    "employee_info_update.main_section.html",
    "hiring_request.main_section.html",
    "late_early_out.main_section.html",
    "outside_work.main_section.html",
    "purchase_request.main_section.html",
    "resignation.main_section.html",
    "special_bonus.main_section.html",
    "system_request.main_section.html",
    # 1D:
    "ai_topup.main_section.html",
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
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
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
                    part.startswith(".ec-shell") or part.startswith("a.ec-shell")
                    or part.startswith("[data-ec-shell")
                    or part.startswith("body.ec-shell-noscroll")
                    or part.startswith("@"),
                    "unscoped CSS selector: %r" % part)

    def test_hooks_include_both_assets_and_keep_nc_first(self):
        hooks = _read(APP, "hooks.py")
        self.assertIn('web_include_js = ["notification_center.bundle.js", "ec_shell.bundle.js"]', hooks)
        self.assertIn('web_include_css = ["ec_shell.bundle.css"]', hooks)


class TestHeaderPolish(unittest.TestCase):
    """Phase 1B.1: header layout, breadcrumb links, branding, no-underline."""

    CRUMB_PAGES = {
        "leave.main_section.html": "Leave",
        "hr_activity.main_section.html": "HR Activity",
        "approvals_dashboard.main_section.html": "Bảng điều hành vận hành",
        "lateral_move.main_section.html": "Employee Lateral Move",
        "promotion.main_section.html": "Promotion Request",
        "employee_referral.main_section.html": "Employee Referral",
        "service_referral.main_section.html": "Service Referral",
        "livestream_supplies.main_section.html": "Livestream Supplies",
        "livestream_sample.main_section.html": "Livestream Sample",
        "affiliate_bonus.main_section.html": "Affiliate Bonus",
        "asset_damage_loss.main_section.html": "Asset Damage or Loss",
        "asset_request.main_section.html": "Asset Request",
        "budget_setting.main_section.html": "Budget Setting",
        "compensation_leave.main_section.html": "Compensation Leave",
        "daily_target.main_section.html": "Daily Target Setting",
        "data_request.main_section.html": "Data Request",
        "document_request.main_section.html": "Document Request",
        "employee_info_update.main_section.html": "Employee Information Update",
        "hiring_request.main_section.html": "Hiring Request",
        "late_early_out.main_section.html": "Late in - Early out",
        "outside_work.main_section.html": "Outside Work",
        "purchase_request.main_section.html": "Purchase Request",
        "resignation.main_section.html": "Resignation Request",
        "special_bonus.main_section.html": "Special Bonus",
        "system_request.main_section.html": "System Request",
        "ai_topup.main_section.html": "AI Topup",
    }

    def test_header_right_slot_on_all_pilots_once(self):
        for fname in PILOT:
            n = _read(FRONTEND, fname).count('data-ec-shell-header-right="1"')
            self.assertEqual(n, 1, "%s must carry exactly one header-right slot" % fname)

    def test_header_right_absent_on_non_pilots(self):
        for fname in sorted(os.listdir(FRONTEND)):
            if fname.endswith(".html") and fname not in PILOT:
                self.assertEqual(
                    _read(FRONTEND, fname).count("data-ec-shell-header-right"), 0, fname)

    def test_breadcrumb_parent_links_to_approvals(self):
        for fname, current in self.CRUMB_PAGES.items():
            src = _read(FRONTEND, fname)
            self.assertIn('<a class="ec-shell-crumblink" href="/approvals">Approval Center</a>',
                          src, fname)
            # current item is plain <strong>, never a self-link
            self.assertIn("<strong>%s</strong>" % current, src, fname)
            self.assertNotIn('href="/approvals/%s"><strong>' % fname.split(".")[0], src)

    def test_hub_breadcrumb_is_current_not_self_linked(self):
        src = _read(FRONTEND, "approvals.main_section.html")
        self.assertIn('<div class="crumb"><strong>Approval Center</strong></div>', src)
        self.assertEqual(src.count("ec-shell-crumblink"), 0,
                         "hub is the breadcrumb root; no parent link")

    def test_bell_single_emission_point_in_js(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        code = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
        self.assertEqual(code.count(BELL), 1,
                         "exactly ONE bell emission point (bellHtml)")
        self.assertIn("renderHeaderRight", js)
        self.assertIn("{ bell: false }", js, "drawer must never render a bell")

    def test_logo_uses_homepage_asset_and_links_root(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("/files/eCentric%20logo%20-%20mini.png", js)
        self.assertIn('href="/"', js, "brand must link to /")
        self.assertNotIn('href="/home"><span class="ec-shell-logo"', js)
        self.assertIn("bindLogoFallback", js, "logo needs a failure fallback")

    def test_no_underline_in_shell_css(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertNotIn("text-decoration:underline", css)
        for scope in (".ec-shell-mount a", ".ec-shell-drawer a", ".ec-shell-tbright a"):
            self.assertIn(scope, css, "explicit no-underline scope missing: " + scope)
        self.assertIn("a.ec-shell-crumblink:hover{ color:#2C3DA6; text-decoration:none; }", css)

    def test_focus_visible_preserved(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(":focus-visible", css)
        self.assertIn("a.ec-shell-crumblink:focus-visible", css)

    def test_action_slot_reserved_not_implemented(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn('data-ec-shell-action-slot="1"', js)
        self.assertIn('aria-hidden="true"', js)
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(".ec-shell-actionslot{ display:none; }", css)


class TestSmoothnessCore(unittest.TestCase):
    """Phase 1C-alpha: boot cache + prefetch + transitions (source contracts;
    behavior is proven in shell/tests/ec_shell_check.js)."""

    def _js(self):
        return _read(APP, "public", "js", "ec_shell.js")

    def test_cache_contract(self):
        js = self._js()
        self.assertIn("sessionStorage", js)
        self.assertIn("CACHE_TTL_MS = 5 * 60 * 1000", js)       # approved TTL
        self.assertIn("'ec_shell_boot_cache_v1'", js)           # versioned key
        self.assertIn("entry.v !== VERSION", js)                # schema/version check
        self.assertIn("cookieUser", js)                         # identity guard
        self.assertIn("cookieUid !== m.user.name", js)
        self.assertIn("JSON.stringify(m) !== JSON.stringify(S.boot)", js)  # SWR diff
        self.assertIn("removeItem(CACHE_KEY)", js)              # disabled -> clear

    def test_cache_never_authorization(self):
        js = self._js()
        # cache path must never skip the backend refresh
        self.assertIn("background refresh", js.lower())
        self.assertNotIn("ignore_permissions", js)

    def test_prefetch_only_no_prerender(self):
        js = self._js()
        self.assertIn("l.rel = 'prefetch'", js)
        low = js.lower()
        # usage tokens, not comment words: no Speculation Rules script type,
        # no prerender rel value anywhere in code.
        self.assertNotIn("speculationrules", low)
        self.assertNotIn("rel = 'prerender'", low)
        self.assertNotIn('rel="prerender"', low)
        self.assertNotIn("'prerender'", low.replace("rel = 'prerender'", ""))

    def test_no_navigation_interception(self):
        js = self._js()
        self.assertNotIn("popstate", js)
        self.assertNotIn("pushState", js)
        self.assertNotIn("preventDefault(); window.location", js)
        self.assertNotIn("document.startViewTransition(", js)   # detect-only, never called

    def test_transition_css(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertIn(".ec-shell-mount~.ec-main{ animation:ec-shell-fadein 120ms ease-out; }", css)
        self.assertIn("@keyframes ec-shell-fadein", css)
        self.assertIn("prefers-reduced-motion", css)


class TestNavSearch(unittest.TestCase):
    """Phase 1C.1: navigation search (source contracts; behavior proven in
    ec_shell_check.js sections 7-8)."""

    def _js(self):
        return _read(APP, "public", "js", "ec_shell.js")

    def test_search_ui_contract(self):
        js = self._js()
        self.assertIn("Tìm chức năng…", js)                    # placeholder
        self.assertIn("ec-shell-search-in", js)
        self.assertIn("'k'", js.lower())                       # Ctrl/Cmd+K
        self.assertIn("ev.ctrlKey || ev.metaKey", js)
        self.assertIn("data-ec-shell-search-clear", js)        # clear button
        self.assertIn("Không tìm thấy chức năng", js)          # empty state
        self.assertIn("ec-shell-hl", js)                       # highlighting

    def test_search_sources_are_permission_filtered_only(self):
        js = self._js()
        # exactly three API endpoints in the whole shell: boot, catalog, logout
        import re
        eps = set(re.findall(r"/api/method/[a-zA-Z0-9_.]+", js))
        self.assertEqual(eps, {
            "/api/method/ecentric_workspace.shell.api.get_shell_boot",
            "/api/method/ecentric_workspace.approval_center.api.catalog.list_catalog",
            "/api/method/logout",
        }, "no business-record search endpoints allowed")
        self.assertIn("c.route; })", js)                       # route-less cards dropped

    def test_catalog_cache_user_isolated(self):
        js = self._js()
        self.assertIn("'ec_shell_catalog_cache_v1'", js)
        self.assertIn("entry.user !== userName", js)
        self.assertIn("user: userName", js)

    def test_registry_keywords_supported(self):
        from ecentric_workspace.shell import nav
        items = nav.compose()
        self.assertTrue(any(it.get("keywords") for it in items))
        bad = dict(items[0], key="x.k", route="/xk", keywords=["ok", ""])
        with self.assertRaises(ValueError):
            nav.validate([bad])

    def test_search_fails_safe(self):
        js = self._js()
        self.assertIn("SEARCH.failed = true", js)              # catalog failure flag
        self.assertIn("catch", js)


if __name__ == "__main__":
    unittest.main()
