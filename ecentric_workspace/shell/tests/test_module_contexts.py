# Copyright (c) 2026, eCentric and contributors
"""Remaining ERP Module Shell Migration acceptance (alert_center/reporting/pm).

Runnable without a bench (frappe stubbed)."""
import io
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
    stub.session = types.SimpleNamespace(user="t@e.c")
    sys.modules["frappe"] = stub

from ecentric_workspace.shell import nav                     # noqa: E402
from ecentric_workspace.alerts import pages as alert_pages   # noqa: E402
from ecentric_workspace.reporting import pages as rep_pages  # noqa: E402
from ecentric_workspace.pm import pages as pm_pages          # noqa: E402


class TestContextOwnership(unittest.TestCase):
    MATRIX = {
        "/alerts": "alert_center", "/alerts/policies": "alert_center",
        "/alerts/rules": "alert_center", "/alerts/locks": "alert_center",
        "/alerts/integration-health": "alert_center",
        "/weekly-update": "reporting", "/weekly-update?week=2026-W29": "reporting",
        "/team-pulse": "reporting",
        "/pm": "pm", "/pm#tasks": "pm",
        "/hall": "home",                       # portal-owned, deferred
        "/": "home", "/approvals": "approval_document", "/ec-hr/salary": "hr",
    }

    def test_resolution_matrix(self):
        for route, ctx in self.MATRIX.items():
            self.assertEqual(nav.resolve_context(route), ctx, route)

    def test_portal_shortcuts_are_alias_only(self):
        home = {i["route"]: i for i in nav.compose("home")}
        for r in ("/alerts", "/weekly-update", "/team-pulse", "/pm"):
            self.assertTrue(home[r].get("alias") is True, r)

    def test_compose_all_unique_and_canonical(self):
        allitems = nav.compose_all()
        routes = [i["route"] for i in allitems]
        self.assertEqual(len(routes), len(set(routes)), "duplicate routes in discovery")
        owners = {i["route"]: i["owner"] for i in allitems}
        self.assertEqual(owners["/alerts"], "alerts")
        self.assertEqual(owners["/weekly-update"], "reporting")
        self.assertEqual(owners["/team-pulse"], "reporting")
        self.assertEqual(owners["/pm"], "pm")
        for r in ("/alerts/policies", "/alerts/rules", "/alerts/locks",
                  "/alerts/integration-health"):
            self.assertEqual(owners[r], "alerts", r)

    def test_each_sidebar_owns_only_its_context(self):
        for ctx, allowed in (("alert_center", {"core", "alerts"}),
                             ("reporting", {"core", "reporting"}),
                             ("pm", {"core", "pm"}),
                             ("hr", {"core", "hr"})):
            self.assertEqual({i["owner"] for i in nav.compose(ctx)}, allowed, ctx)
        appr = {i["owner"] for i in nav.compose("approval_document")}
        self.assertFalse(appr & {"alerts", "reporting", "pm", "hr", "home_portal"})

    def test_home_and_hall_unchanged_portal(self):
        home = nav.compose("home")
        self.assertEqual(len(home), 16)
        hall = next(i for i in home if i["route"] == "/hall")
        self.assertNotIn("alias", hall)   # /hall stays canonical portal-owned


ALERT_FIXTURE = ('<style>.x{}</style><div class="ecentric-app">'
                 '<aside class="ec-sidebar"><nav>old alert nav</nav></aside>'
                 '<main><div class="topbar">\n  <div class="breadcrumb">Workspace / <strong>Alert Center</strong> / Rules</div>\n'
                 '  <div class="topbar-actions">\n    <a href="/help" class="icon-btn"><svg></svg></a>\n'
                 '    <a data-ec-notification-bell="1" href="/app/notification-log" class="icon-btn"><svg></svg><span class="dot"></span></a>\n'
                 '  </div>\n</div>'
                 '<div class="content">BUSINESS<table id="al-rules"></table>'
                 '<script id="ec-csrf-fetch-patch">c()</script>'
                 '<script id="ec-alert-shared">a()</script></div></main></div>')


class TestAlertTransform(unittest.TestCase):
    def test_zones_swapped_business_preserved(self):
        new = alert_pages.transform(ALERT_FIXTURE, "alerts/rules")
        self.assertIn('BUSINESS<table id="al-rules">', new)
        self.assertNotIn('class="ec-sidebar"', new)
        self.assertNotIn('href="/help"', new)
        self.assertEqual(new.count('data-ec-notification-bell="1"'), 1)
        self.assertIn('<div class="ec-shell-grouplabel">Alert Center</div>', new)
        self.assertIn('<strong class="ec-shell-crumb-current">Rules</strong>', new)
        again = alert_pages.transform(new, "alerts/rules")
        self.assertEqual(again, new, "idempotent")

    def test_refuses_when_business_script_missing(self):
        with self.assertRaises(ValueError):
            alert_pages.transform(ALERT_FIXTURE.replace("ec-alert-shared", "x"), "alerts/rules")


def _rep_fixture(extra_aside):
    return ('<div class="ecentric-app">'
            '<aside class="ec-sidebar"><nav>stale home clone</nav></aside>'
            '<main><div class="topbar">\n<div class="breadcrumb"><strong>X</strong></div>\n</div>'
            '<div class="content">{% if x %}J{% endif %}<div id="wtu-form"></div>'
            '<script id="ec-csrf-fetch-patch">c()</script>'
            '<script id="wu-week-nav-js">w()</script>'
            '<script id="tp-company-summary-js">t()</script>'
            '<script id="ec-chatbot-js">g()</script>' + extra_aside + '</div></main></div>')


class TestReportingTransform(unittest.TestCase):
    def test_wu_gets_first_bell_and_keeps_jinja(self):
        src = _rep_fixture('<aside class="wu-roadmap" id="wu-roadmap" hidden>R</aside>')
        new = rep_pages.transform(src, "weekly-update")
        self.assertEqual(new.count('data-ec-notification-bell="1"'), 1)
        # UAT hotfix: shell-isolation zone injected exactly once, CSS-only,
        # re-asserting canonical geometry against the pages' generic selectors
        self.assertEqual(new.count('<style id="ec-reporting-shell-isolation">'), 1)
        zone = rep_pages.ISOLATION_RE.search(new).group(0)
        self.assertNotIn("<script", zone)
        for sel in (".ec-shell-mount{", ".ec-shell-search-in{", "a.ec-shell-item{",
                    ".ec-shell-topbar{", ".ec-shell-tbright{"):
            self.assertIn(sel, zone, sel)
        self.assertNotIn("display:none", zone)
        self.assertIn("{% if x %}J{% endif %}", new)
        self.assertIn('<aside class="wu-roadmap" id="wu-roadmap" hidden>R</aside>', new)
        self.assertNotIn("stale home clone", new)
        self.assertIn('<strong class="ec-shell-crumb-current">Báo cáo tuần</strong>', new)
        self.assertEqual(rep_pages.transform(new, "weekly-update"), new)

    def test_tp_business_aside_survives(self):
        src = _rep_fixture('<aside class="tp-ai-panel" id="tp-ai-panel">AI</aside>')
        new = rep_pages.transform(src, "team-pulse")
        self.assertIn('id="tp-ai-panel">AI</aside>', new)
        self.assertIn('<div class="ec-shell-grouplabel">Báo cáo &amp; Phân tích</div>', new)


PM_FIXTURE = ('<style>#ec-pm-root{display:grid;grid-template-columns:248px 1fr;}</style>'
              '<div id="ec-pm-root">'
              '<aside class="ec-sidebar"><div class="sidebar-header"><a href="/home" class="brand">B</a></div>'
              '<div class="sidebar-search"><input type="text" id="pm-search"></div>'
              '<nav class="nav-section" id="pm-nav"><div class="nav-label">QLDA</div>'
              '<a class="nav-item" data-view="dashboard"><span>DB</span></a>'
              '<a class="nav-item" data-view="mytasks"><span>MT</span></a>'
              '<div class="nav-label" style="margin-top:10px;">Khác</div>'
              '<a class="nav-item" href="/home"><span>Trang chủ</span></a></nav>'
              '<div class="sidebar-footer"><a href="/app/user" class="user-card"><div class="avatar">A</div></a></div></aside>'
              '<main><div class="topbar">'
              '<div class="breadcrumb">Project Management / <strong id="pm-crumb">Tổng quan</strong></div>'
              '<div class="topbar-actions"><span class="preview-tag" id="pm-preview"></span>'
              '<button class="tb-timer" id="tb-timer"></button>'
              '<button class="pm-btn primary" id="tb-new">New</button>'
              '<a class="icon-btn" id="tb-bell" href="/app/notification-log" data-ec-notification-bell="1"><svg></svg></a>'
              '<button class="icon-btn" title="Cài đặt"><svg></svg></button>'
              '</div></div>'
              '<div class="content">SPA BODY'
              '<script>// binds data-ec-notification-bell="1" via marker</script>'
              '</div></main></div>')


class TestPMTransform(unittest.TestCase):
    def test_spa_safe_dual_rail(self):
        new = pm_pages.transform(PM_FIXTURE)
        # SPA internals byte-exact
        self.assertIn('<nav class="nav-section" id="pm-nav"><div class="nav-label">QLDA</div>'
                      '<a class="nav-item" data-view="dashboard"><span>DB</span></a>'
                      '<a class="nav-item" data-view="mytasks"><span>MT</span></a>', new)
        self.assertEqual(new.count('id="pm-search"'), 1)
        # chrome trimmed: brand/footer/back-entry gone; shell mount added
        self.assertNotIn('class="sidebar-header"', new)
        self.assertNotIn('class="sidebar-footer"', new)
        self.assertNotIn('<a class="nav-item" href="/home">', new)
        self.assertEqual(new.count('data-ec-shell="1"'), 1)
        # business topbar controls preserved; settings stub gone
        for keep in ('id="tb-timer"', 'id="tb-new"', 'id="pm-preview"'):
            self.assertIn(keep, new)
        self.assertNotIn('title="Cài đặt"', new)
        # crumbs canonical with live pm-crumb detail; the legacy static
        # "Project Management / " prefix (the 417 root cause) is dropped in
        # favour of registry crumbs
        self.assertIn('data-ec-shell-crumb-detail="1" id="pm-crumb">Tổng quan</strong>', new)
        self.assertNotIn("Project Management / <strong", new)
        # exactly ONE bell ELEMENT (JS string mention ignored)
        self.assertEqual(len(re.findall(r'<[a-zA-Z][^>]*data-ec-notification-bell="1"', new)), 1)
        self.assertIn('binds data-ec-notification-bell', new)  # JS string untouched
        self.assertIn('<style id="ec-pm-shell-grid">', new)
        again = pm_pages.transform(new)
        self.assertEqual(again, new, "idempotent")

    def test_refuses_without_spa_anchors(self):
        with self.assertRaises(ValueError):
            pm_pages.transform(PM_FIXTURE.replace('id="pm-nav"', 'id="x"'))

    def test_pm_injected_markup_is_jinja_safe(self):
        """Production incident 2026-07-23: /pm is Jinja-rendered; injected
        minified CSS emitted '){#ec-pm-root' -> unterminated Jinja comment ->
        TemplateSyntaxError. EVERY injected shell fragment must be free of
        Jinja delimiters ({#, {{, {%) unless explicitly approved."""
        import types
        from ecentric_workspace.shell import fallback as fb
        frags = {
            "GRID_STYLE": pm_pages.GRID_STYLE,
            "mount(/pm)": fb.render_mount_inner("/pm"),
            "tbright": fb.render_tbright_inner(),
            "crumbs(/pm)": fb.crumbs_inner("/pm"),
            "reporting ISOLATION_STYLE": rep_pages.ISOLATION_STYLE,
            "reporting topbar(/weekly-update)": fb.render_topbar_inner("/weekly-update"),
            "alerts topbar(/alerts)": fb.render_topbar_inner("/alerts"),
        }
        for what, frag in frags.items():
            for d in ("{#", "{{", "{%"):
                self.assertNotIn(d, frag, "%s contains Jinja delimiter %r" % (what, d))
        # runtime guard wired into the transform itself
        import inspect
        src = inspect.getsource(pm_pages)
        self.assertIn('JINJA_DELIMS = ("{#", "{{", "{%")', src)
        self.assertIn('_assert_jinja_safe(GRID_STYLE', src)
        # end-to-end: transformed output adds NO new Jinja tokens
        new = pm_pages.transform(PM_FIXTURE)
        for d in ("{#", "{{", "{%"):
            self.assertEqual(new.count(d), PM_FIXTURE.count(d), d)

    def test_pm_repairs_broken_migrated_state_idempotently(self):
        """The failed production state = migrated page carrying the OLD
        minified grid zone (with '{#'). Re-running the transform must strip
        it and inject the fixed zone (repair-in-place)."""
        good = pm_pages.transform(PM_FIXTURE)
        broken = pm_pages.GRID_RE.sub(
            '<style id="ec-pm-shell-grid">#ec-pm-root{grid-template-columns:auto 248px 1fr !important;}'
            '@media (max-width:1100px){#ec-pm-root{grid-template-columns:auto 1fr !important;}}</style>',
            good, count=1)
        self.assertIn("{#", broken)
        repaired = pm_pages.transform(broken)
        self.assertNotIn("{#", repaired)
        self.assertEqual(repaired, good, "repair must converge to the fixed canonical state")
        self.assertEqual(pm_pages.transform(repaired), repaired, "idempotent after repair")

    def test_guard_rejects_element_before_crumb(self):
        # [^<]* accepts TEXT prefix only; an unknown ELEMENT keeps refusal
        bad = PM_FIXTURE.replace('Project Management / <strong id="pm-crumb">',
                                 '<span>PM</span><strong id="pm-crumb">')
        with self.assertRaises(ValueError):
            pm_pages.transform(bad)


if __name__ == "__main__":
    unittest.main()
