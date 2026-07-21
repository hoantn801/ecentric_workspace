# Copyright (c) 2026, eCentric and contributors
"""Navigation contexts: scoped sidebar, global discovery, central no-warm
policy, static/hydrated parity (architecture correction 2026-07-21)."""
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

from ecentric_workspace.shell import fallback as fb    # noqa: E402
from ecentric_workspace.shell import nav               # noqa: E402
from ecentric_workspace.shell import route_policy      # noqa: E402


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TestRouteToContext(unittest.TestCase):
    MATRIX = {
        "/approvals": "approval_document",
        "/approvals/leave": "approval_document",
        "/approval": "approval_document",
        "/all-ticket": "approval_document",
        "/form-po": "approval_document",
        "/docs/gbs-flow": "approval_document",
        "/ec-hr/attendance": "hr",
        "/ec-hr/salary": "hr",
        "/": "home",
        "/home": "home",
        "/weekly-update": "approval_document",   # unregistered -> DEFAULT
    }

    def test_resolution_matrix(self):
        for route, ctx in self.MATRIX.items():
            self.assertEqual(nav.resolve_context(route), ctx, route)

    def test_context_isolation(self):
        appr = nav.compose("approval_document")
        self.assertFalse(any(i["owner"] == "hr" for i in appr),
                         "Approval sidebar must contain ZERO HR entries")
        hr = nav.compose("hr")
        owners = {i["owner"] for i in hr}
        self.assertEqual(owners, {"core", "hr"},
                         "HR sidebar must contain zero Approval/Document entries")
        self.assertEqual([i["label"] for i in hr if i["owner"] == "hr"],
                         ["Chấm công", "Phiếu lương"])

    def test_home_launcher_from_context_metadata(self):
        home = nav.compose("home")
        launcher = [i for i in home if i["group"] == nav.LAUNCHER_GROUP]
        self.assertEqual([i["label"] for i in launcher],
                         ["Phê duyệt & Chứng từ", "Nhân sự"])
        for i in launcher:
            self.assertEqual(i["owner"], "shell.context")
            name = i["key"].split(".", 1)[1]
            self.assertEqual(i["route"], nav.CONTEXTS[name]["entry"]["route"],
                             "launcher entry must come from CONTEXTS metadata")
        self.assertIn("core.home", [i["key"] for i in home])

    def test_compose_all_spans_contexts(self):
        allr = {i["route"] for i in nav.compose_all()}
        for r in ("/approvals", "/form-po", "/ec-hr/attendance", "/ec-hr/salary"):
            self.assertIn(r, allr, r)
        # synthetic launcher entries are discovery-excluded (route dupes)
        self.assertFalse(any(i["owner"] == "shell.context" for i in nav.compose_all()))

    def test_future_context_registrable_without_core_change(self):
        # adding a context = data-only: CONTEXTS entry + provider registration
        self.assertIsInstance(nav.CONTEXTS, dict)
        self.assertIsInstance(nav.CONTEXT_ORDER, list)
        for name in nav.CONTEXT_ORDER:
            self.assertIn("providers", nav.CONTEXTS[name])
            self.assertIn("entry", nav.CONTEXTS[name])


class TestSalaryNeverWarmable(unittest.TestCase):
    """Visible/discoverable but NEVER warmable -- independent of nav ownership."""

    def test_policy_is_nav_independent(self):
        self.assertTrue(route_policy.no_warm("/ec-hr/salary"))
        self.assertTrue(route_policy.no_warm("/ec-hr/salary/2026-06"))
        self.assertFalse(route_policy.no_warm("/ec-hr/attendance"))
        # policy module must not import nav (ownership independence)
        src = _read(APP, "shell", "route_policy.py")
        self.assertNotIn("import nav", src)
        self.assertNotIn("shell.nav", src)

    def test_boot_serialization_derives_from_policy_even_without_item_flag(self):
        src = _read(APP, "shell", "api.py")
        self.assertIn('bool(it.get("no_prerender")) or route_policy.no_warm(it["route"])', src)

    def test_salary_discoverable_everywhere(self):
        self.assertIn("/ec-hr/salary", {i["route"] for i in nav.compose_all()})
        self.assertIn("/ec-hr/salary", {i["route"] for i in nav.compose("hr")})
        qa = fb.render_quickaccess_inner()
        self.assertIn('href="/ec-hr/salary"', qa, "salary stays in Quick Access")
        # NOTE (Homepage Sync Safety Hotfix): the authored cockpit homepage was
        # retired; no repo page renders the quick-access marker until the
        # incremental Homepage migration phase. The renderer contract above
        # remains the governed discovery surface.

    def test_salary_excluded_from_all_three_warming_paths(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        # 1+2: prefetch allow-list + eager warming share knownNavRoutes
        self.assertIn("!it.no_prerender", js)
        self.assertIn("knownNavRoutes()", js)
        # 3: Speculation Rules list
        self.assertIn("if (it.no_prerender) return;", js)
        # page-level protections preserved by the HR sync guards
        sb = _read(APP, "hr", "pages", "shell_boundary.py")
        self.assertIn('"ec-salary-noprerender"', sb)
        self.assertIn('"ec-hr-salary"', sb)


class TestStaticHydratedContextParity(unittest.TestCase):
    def test_fallback_uses_resolve_context(self):
        src = _read(APP, "shell", "fallback.py")
        self.assertEqual(src.count("shell_nav.compose(shell_nav.resolve_context(route))"), 2,
                         "mount + crumbs must both be context-scoped")

    def test_js_ports_resolution(self):
        js = _read(APP, "public", "js", "ec_shell.js")
        for frag in ("function resolveContext(boot, pathname)",
                     "boot.context_order", "boot.default_context",
                     "resolveContext: resolveContext"):
            self.assertIn(frag, js, frag)
        # sidebar renders the RESOLVED context; discovery uses allItems
        self.assertIn("navHtml((S.ctxNav || boot.nav), activeKey)", js)
        self.assertIn("buildSearchEntries(S.boot && allItems(S.boot), SEARCH.types)", js)
        self.assertIn("prerenderUrls(S.boot && (S.ctxNav || S.boot.nav)", js)

    def test_static_pages_match_their_context(self):
        for path, route in sorted(fb.page_route_map(REPO).items()):
            src = _read(path)
            ctx = nav.resolve_context(route)
            has_hr_group = '<div class="ec-shell-grouplabel">Nhân sự</div>' in src
            has_appr_group = '<div class="ec-shell-grouplabel">Tạo mới</div>' in src
            has_launcher = '<div class="ec-shell-grouplabel">Phân hệ</div>' in src
            if ctx == "approval_document":
                self.assertTrue(has_appr_group and not has_hr_group and not has_launcher, route)
            elif ctx == "home":
                self.assertTrue(has_launcher and not has_appr_group and not has_hr_group, route)

    def test_hr_boundary_sync_contracts(self):
        sb = _read(APP, "hr", "pages", "shell_boundary.py")
        self.assertIn("System Manager", sb)                      # SM-gated
        self.assertIn("_strip_zones(ms_clean) != _strip_zones(new)", sb)  # byte proof
        self.assertIn("STRAY_LT_RE", sb)  # stray-literal repair (attendance regression)
        self.assertIn('render_mount_inner("/" + route)', sb)     # canonical renderer
        self.assertIn("sync_hr_attendance_page", sb)
        self.assertIn("sync_hr_salary_page", sb)


if __name__ == "__main__":
    unittest.main()
