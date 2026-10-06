# Copyright (c) 2026, eCentric and contributors
"""Homepage Shared Shell (Preserve UX) contracts.

- 3-tier portal model: visible IA vs canonical discovery vs coming-soon.
- 29/09/2026: the homepage SOURCE lives in the repo (legacy_pages/home/main_section.html,
  NHIEU_LOP phase 2). The shell zones that transform_home used to splice into the live page
  (canonical mount + topbar + polish) are now plain source, kept canonical by the shell
  drift gate (fallback.regenerate, route "/"). Cockpit markup can never return.
Runnable without a bench (frappe stubbed)."""
import importlib
import io
import os
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

from ecentric_workspace.shell import nav                       # noqa: E402
from ecentric_workspace.shell import route_policy              # noqa: E402


class TestThreeTierModel(unittest.TestCase):
    def test_coming_soon_visible_but_undiscoverable(self):
        home = nav.compose("home")
        soon = [i for i in home if i.get("soon")]
        # kpi, 2x tài nguyên (đào tạo, góp ý). "Tuyển dụng" rời nhóm này
        # 2026-08-11 (trang thật /ec-app/hr/recruitment); "Tổng quan" rời 2026-09-28
        # (trang thật /tong-quan); "Intranet" thành "Tin nội bộ" 2026-10-01 (/tin-noi-bo).
        # "Góp ý BGD" thành "Góp ý công ty" 2026-10-04 (/gop-y).
        self.assertEqual(len(soon), 2)
        allr = {i["route"] for i in nav.compose_all()}
        for i in soon:
            self.assertNotIn(i["route"], allr, i["key"])
        self.assertFalse(any("coming-soon" in r for r in allr))

    def test_aliases_visible_but_not_duplicated_in_discovery(self):
        allitems = nav.compose_all()
        routes = [i["route"] for i in allitems]
        self.assertEqual(len(routes), len(set(routes)), "discovery must be dupe-free")
        owners = {i["route"]: i["owner"] for i in allitems}
        self.assertEqual(owners["/approvals"], "approval_center")
        self.assertEqual(owners["/ec-hr/salary"], "hr")
        self.assertFalse(any(i["owner"] == "home_portal" and i.get("alias")
                             for i in allitems))

    def test_approved_live_routes_now_discoverable(self):
        # module contexts (2026-07-22) took canonical ownership of 4 routes;
        # /hall + /approvals/leave stay portal-canonical
        allr = {i["route"]: i["owner"] for i in nav.compose_all()}
        self.assertEqual(allr.get("/hall"), "home_portal")
        self.assertEqual(allr.get("/approvals/leave"), "home_portal")
        self.assertEqual(allr.get("/pm"), "pm")
        self.assertEqual(allr.get("/weekly-update"), "reporting")
        self.assertEqual(allr.get("/team-pulse"), "reporting")
        self.assertEqual(allr.get("/alerts"), "alerts")

    def test_salary_discoverable_never_warmable(self):
        self.assertIn("/ec-hr/salary", {i["route"] for i in nav.compose_all()})
        self.assertTrue(route_policy.no_warm("/ec-hr/salary"))
        # portal alias link cannot re-enable warming (policy is route-based)
        sal = next(i for i in nav.compose("home") if i["route"] == "/ec-hr/salary")
        self.assertTrue(route_policy.no_warm(sal["route"]))

    def test_approval_nav_badge_via_governed_badge_source(self):
        """Preserve-UX: the legacy approvals_count Jinja badge survives as a
        governed badge_source on the portal item -- same semantics: user-
        scoped count from the EXISTING shared action provider, zero hides."""
        appr = next(i for i in nav.compose("home") if i["key"] == "home.portal.approvals")
        self.assertEqual(appr.get("badge_source"), "action_center.approvals")
        # no other portal item grows a badge
        others = [i for i in nav.compose("home") if i["key"] != "home.portal.approvals"]
        self.assertFalse(any(i.get("badge_source") for i in others))
        js = io.open(os.path.join(APP, "public", "js", "ec_shell.js"), encoding="utf-8").read()
        # registered-key resolver, session-scoped provider, zero-hides contract
        self.assertIn("'action_center.approvals': {", js)
        self.assertIn("ecentric_workspace.action_center.api.get_action_items", js)
        # Binds the AUTHORITATIVE feed.source_counts.approval (identical to the
        # homepage KPI, excludes fulfillment). The old client-side item filter
        # items.filter(source_type==='approval') -- which double-counted
        # fulfillment items -- is removed.
        self.assertIn("msg.source_counts", js)
        self.assertIn("sc.approval", js)
        self.assertNotIn("=== 'approval'", js)
        self.assertIn("if (n > 0)", js, "zero must keep the badge hidden")
        self.assertIn('data-ec-shell-badge="', js)
        self.assertIn("never a raw URL from the payload", js)
        css = io.open(os.path.join(APP, "public", "css", "ec_shell.bundle.css"), encoding="utf-8").read()
        self.assertIn(".ec-shell-badge{", css)
        # boot serialization carries the field
        api = io.open(os.path.join(APP, "shell", "api.py"), encoding="utf-8").read()
        self.assertIn('"badge_source": it.get("badge_source") or ""', api)
        # the homepage KPI card stays a widget-owned placeholder (no server count)
        src = io.open(os.path.join(APP, "legacy_pages", "home", "main_section.html"), encoding="utf-8").read()
        self.assertIn('<div class="stat-value" data-ec-ac-kpi="approval">—</div>', src)

    def test_module_contexts_unchanged(self):
        self.assertFalse(any(i["owner"] == "home_portal"
                             for i in nav.compose("approval_document")))
        self.assertFalse(any(i["owner"] == "home_portal" for i in nav.compose("hr")))


class TestHomeShellZones(unittest.TestCase):
    """The homepage source carries the canonical shell chrome; business/Jinja kept."""

    def _src(self):
        return io.open(os.path.join(APP, "legacy_pages", "home", "main_section.html"), encoding="utf-8").read()

    def test_canonical_chrome_only(self):
        new = self._src()
        for keep in ('{{ first_name|e }}', 'ecentricCheckin()', '{% for n in ec_news %}',
                     'ec-action-center-widget', 'ec-csrf-fetch-patch'):
            self.assertIn(keep, new, keep)
        self.assertNotIn('class="ec-sidebar"', new)
        self.assertNotIn('<div class="topbar">', new)
        self.assertNotIn('href="/help"', new)
        self.assertNotIn('href="/app/user-settings" class="icon-btn"', new)
        self.assertEqual(new.count('data-ec-shell="1"'), 1)
        self.assertEqual(new.count('data-ec-shell-topbar="1"'), 1)
        self.assertEqual(new.count('data-ec-notification-bell="1"'), 0)
        self.assertEqual(new.count('data-ec-shell-action-slot="1"'), 1)
        for g in ("Workspace", "Nhân sự", "Báo cáo &amp; Phân tích", "Tài nguyên"):
            self.assertIn('<div class="ec-shell-grouplabel">%s</div>' % g, new, g)
        self.assertIn('href="/ec-hr/attendance"', new)
        self.assertIn("ec-shell-item-soon", new)
        # "/" is the homepage: the crumb is the CURRENT item, not a link to itself
        self.assertIn('<strong class="ec-shell-crumb-current">Trang chủ</strong>', new)

    def test_shell_zones_have_no_drift(self):
        from ecentric_workspace.shell import fallback as fb
        rm = fb.page_route_map(REPO)
        home = [p for p in rm if p.replace(os.sep, "/").endswith("legacy_pages/home/main_section.html")]
        self.assertEqual(len(home), 1)
        self.assertEqual(rm[home[0]], "/")
        changed, _ = fb.regenerate(REPO, check=True)
        self.assertFalse([c for c in changed if "legacy_pages" in c and "home" in c],
                         "run: python -m ecentric_workspace.shell.fallback --repo .")

    def test_cockpit_markup_absent(self):
        new = self._src()
        for mk in ('class="ec-ck', "ec-cockpit-js", "ec-ck-grid", "data-ec-shell-quickaccess"):
            self.assertNotIn(mk, new, mk)

    def test_portal_icons_distinct_and_routes_kept(self):
        icons = [i["icon"] for i in nav.compose("home")]
        self.assertEqual(len(icons), len(set(icons)), "portal icons must be distinct")
        labels = {i["label"]: i["route"] for i in nav.compose("home")}
        self.assertEqual(labels["Phê duyệt"], "/approvals")
        self.assertEqual(labels["Chấm công"], "/ec-hr/attendance")
        self.assertEqual(labels["Phiếu lương"], "/ec-hr/salary")
        self.assertEqual(labels["Nghỉ phép"], "/approvals/leave")

    def test_jinja_and_dynamic_template_preserved(self):
        src = io.open(os.path.join(APP, "legacy_pages", "home", "page_sync.py"),
                      encoding="utf-8").read()
        self.assertNotIn("ensure_static_serving", src)
        self.assertIn('"dynamic_template", 1', src)
        self.assertIn("{% set user_email = frappe.session.user %}", self._src())


if __name__ == "__main__":
    unittest.main()
