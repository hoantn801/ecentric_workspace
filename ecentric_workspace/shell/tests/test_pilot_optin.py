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
    # 1E:
    "payment_request.main_section.html",
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

    def test_pilot_pages_have_full_static_shell(self):
        # Smoothness Stabilization: fallback = COMPLETE server-rendered shell
        # (same registry, same classes) -- visible from first paint.
        for fname in PILOT:
            src = _read(FRONTEND, fname)
            self.assertIn('ec-shell-fallback', src, fname)
            for marker in ('class="ec-shell-head"', "ec-shell-search-in",
                           'class="ec-shell-foot"', "ec-shell-grouplabel",
                           'href="/approvals"', 'href="/all-ticket"',
                           "ec-shell-active"):
                self.assertIn(marker, src, "%s missing %s" % (fname, marker))

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
        "payment_request.main_section.html": "Payment Request",
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

    def test_pages_carry_exactly_one_static_bell(self):
        # static bell lives in the header-right slot so NC works pre-hydration
        for fname in PILOT:
            src = _read(FRONTEND, fname)
            self.assertEqual(src.count(BELL), 1, fname)
            i_tb = src.index('data-ec-shell-header-right="1"')
            self.assertGreater(src.index(BELL), i_tb, fname + ": bell must be in tbright")
        js = _read(APP, "public", "js", "ec_shell.js")
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

    def test_prefetch_still_present(self):
        # v1.6.0: prefetch kept (effective on the CACHEABLE /approvals pages);
        # prerender ADDED for the no-store T4 pages (see test_prerender_*).
        js = self._js()
        self.assertIn("l.rel = 'prefetch'", js)
        # rel="prerender" (the deprecated link-rel form) is NOT used; we use the
        # modern Speculation Rules API instead.
        self.assertNotIn("rel = 'prerender'", js)
        self.assertNotIn('rel="prerender"', js)

    def test_no_navigation_interception(self):
        js = self._js()
        self.assertNotIn("popstate", js)
        self.assertNotIn("pushState", js)
        self.assertNotIn("preventDefault(); window.location", js)
        self.assertNotIn("document.startViewTransition(", js)   # detect-only, never called

    def test_transition_css_removed(self):
        css = _read(APP, "public", "css", "ec_shell.bundle.css")
        self.assertNotIn("ec-shell-fadein", css)


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


class TestPaymentRequestComposition(unittest.TestCase):
    """Phase 1E: the SCTS composition (page_sync appends signing panel +
    requester panel + coords + PDF editor AFTER the main section) must be
    unchanged and correctly ordered around the shell-migrated main html."""

    def _composed(self):
        import sys, types, importlib
        fake = types.ModuleType("frappe")
        fake.whitelist = lambda **kw: (lambda fn: fn)
        fake._ = lambda s: s
        fake.db = types.SimpleNamespace(exists=lambda *a: False)
        fake.session = types.SimpleNamespace(user="t@e.vn")
        fake.get_roles = lambda u=None: []
        fake.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a))
        sys.modules.setdefault("frappe", fake)
        for mod in ("ecentric_workspace.approval_center.page_sync_util",
                    "ecentric_workspace.approval_center.payment_request.page_sync"):
            sys.modules.pop(mod, None)
        ps = importlib.import_module(
            "ecentric_workspace.approval_center.payment_request.page_sync")
        return ps._html()

    def test_composition_markers_and_order(self):
        # Updated 2026-07-16 for the upstream A2 composition (PR#173/174):
        # main + hidden ec-approver-wrap(ec-esign-panel) + unified ec-docsign
        # section; requester raw panel + inline editor removed upstream
        # (Phase C re-introduces a governed editor inside the drawer).
        html = self._composed()
        marker = html.index('data-ec-shell="1"')
        content = html.index('<div class="content">')
        wrap = html.index('id="ec-approver-wrap"')
        panel = html.index('id="ec-esign-panel"')
        docsign = html.index('id="ec-docsign"')
        self.assertTrue(marker < content < wrap < panel < docsign,
                        "composition order changed")
        self.assertEqual(html.count('data-ec-shell="1"'), 1)
        self.assertEqual(html.count('data-ec-shell-header-right="1"'), 1)
        self.assertEqual(html.count('id="ec-approver-wrap"'), 1)
        self.assertEqual(html.count('id="ec-esign-panel"'), 1)
        self.assertEqual(html.count('id="ec-docsign"'), 1)

    def test_no_esign_selector_depends_on_replaced_markup(self):
        base = os.path.join(APP, "approval_center", "esign", "ui")
        for f in ("payment_request_signing.html", "requester_signing_panel.html",
                  "pdf_placement_editor.html", "document_signing_section.html"):
            src = _read(base, f)
            # scan CODE only: drop //-comment lines (A2's document section
            # DOCUMENTS its anti-coupling rule in comments mentioning the
            # shell selectors -- that is the opposite of coupling).
            code = "\n".join(l for l in src.splitlines()
                              if not l.strip().startswith("//"))
            for sel in ('ec-sidebar', 'class="topbar"', '.crumb', 'ec-shell'):
                self.assertNotIn(sel, code, "%s couples to shell markup: %s" % (f, sel))


class TestSidebarStickyAndInstantNav(unittest.TestCase):
    """UX follow-up: sticky sidebar regions + no-fallback-flash contracts."""

    def _css(self):
        return _read(APP, "public", "css", "ec_shell.bundle.css")

    def test_only_nav_scrolls(self):
        css = self._css()
        self.assertIn("position:sticky; top:0; height:100vh; overflow:hidden;", css)
        self.assertIn(".ec-shell-nav{ flex:1 1 auto; min-height:0; overflow-y:auto;", css)
        self.assertIn(".ec-shell-head, .ec-shell-search, .ec-shell-foot{ flex:0 0 auto; }", css)

    def test_drawer_inner_scroll(self):
        self.assertIn("overflow:hidden;   /* inner nav scrolls, not the drawer */", self._css())

    def test_shell_typography_lock(self):
        # Measured leak (2026-07-20): /docs/gbs-flow rendered the sidebar in
        # InterVariable via font INHERITANCE (page parent chains differ; some
        # pages carry universal DM-Sans rules). Shell ROOTS must declare
        # explicit typography; only the search input may inherit (it picks up
        # the locked stack from the roots).
        css = self._css()
        self.assertIn("font-family: Inter, system-ui, sans-serif;", css)
        self.assertIn("letter-spacing: normal;", css)
        self.assertIn("line-height: 1.5;", css)
        self.assertEqual(css.count("font-family:inherit"), 1)
        i = css.index("font-family:inherit")
        self.assertIn("ec-shell-search-in", css[max(0, i - 200):i])

    def test_no_reveal_or_fade_masking(self):
        # Smoothness Stabilization: masking is FORBIDDEN. The static shell is
        # visible from first paint; hydration must not need any hiding.
        css = self._css()
        self.assertNotIn("ec-shell-reveal", css)
        self.assertNotIn("ec-shell-fadein", css)
        self.assertNotIn(".ec-shell-fallback{ opacity:0", css)

    def test_prefetch_covers_registry_routes(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("function shouldPrefetch(href, origin, knownRoutes)", js)
        self.assertIn("knownNavRoutes()", js)

    def test_eager_intent_prerender(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        self.assertIn("eagerPrerender", js)
        self.assertIn("eagerness: 'eager'", js)
        self.assertIn("data-ec-shell-spec-eager", js)
        self.assertIn("'focusin'", js)

    def test_fallback_parity_with_js(self):
        # fallback.py must render the same icon paths + classes as ec_shell.js
        from ecentric_workspace.shell import fallback as fb
        js = _read(APP, "public", "js", "ec_shell.js")
        for name, path in fb.ICONS.items():
            self.assertIn(path, js, "icon %s diverged from ec_shell.js" % name)
        inner = fb.render_mount_inner("/approvals/leave")
        for cls in ("ec-shell-head", "ec-shell-search", "ec-shell-nav",
                    "ec-shell-item", "ec-shell-foot", "ec-shell-subtoggle",
                    "ec-shell-children"):
            self.assertIn(cls, inner, cls)
        self.assertNotIn("data-ec-notification-bell", inner,
                         "mount fallback must NOT carry a bell (tbright owns it)")

    def test_prerender_speculation_rules(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        # Speculation Rules prerender (the only lever that works on no-store T4
        # pages) -- feature-detected, list-based, moderate eagerness.
        self.assertIn("HTMLScriptElement.supports('speculationrules')", js)
        self.assertIn("type = 'speculationrules'", js)
        self.assertIn("eagerness: 'moderate'", js)
        self.assertIn("source: 'list'", js)
        # never intercept navigation
        self.assertNotIn("preventDefault(); window.location", js)


if __name__ == "__main__":
    unittest.main()
