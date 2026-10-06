# Copyright (c) 2026, eCentric and contributors
"""Menu 2 tang: thanh khu vuc navy + cot trang (07/10/2026, PO Hoan duyet mockup C2).

Khoa 6 dieu:
1. Registry RAIL hop le: moi ngu canh (tru `home`) thuoc DUNG mot khu; moi `keys` ton tai.
2. Trang nao bat khu nao, cot hien gi (bang route -> khu -> danh sach muc), ke ca
   MSO / SO / PO hien san ngay duoi nhom Phe duyet (PO 07/10).
3. Kill switch `ec_shell_rail_disabled` -> markup menu 1 cot CU, khong thuoc tinh data-ec-rail.
4. Ban server (fallback.rail_view / rail_html) giong HET ban JS (railView / railHtml /
   navHtml / navSig) -> client giu nguyen DOM server.
5. Hydrate that trong jsdom: trang server ve san -> khong ve lai; boot.rail = null (vua
   bat kill switch) -> ve lai menu 1 cot va GO thuoc tinh data-ec-rail.
6. Boot API mang `rail` = rail_spec() hoac None theo cung cong tac voi server.

Chay:  python3 -m unittest ecentric_workspace.shell.tests.test_shell_rail
Phan JS can `node` (+ `jsdom` cho hydrate); thieu thi SKIP kem ly do.
"""
import re
import sys
import unittest

from ecentric_workspace.shell.tests import test_server_nav as T

#: So test trong file (lech = co test khong nap).
EXPECT_TOTAL = 14

_SAVED = {}


def _forget(names):
    """Bo module khoi sys.modules VA khoi thuoc tinh cua package: `from pkg import mod`
    lay thuoc tinh package truoc, nen chi pop sys.modules thi lan import sau van ra module
    cu (gan voi frappe gia cua file test khac)."""
    import importlib
    for name in names:
        sys.modules.pop(name, None)
        pkg, _, attr = name.rpartition(".")
        mod = sys.modules.get(pkg) or importlib.import_module(pkg)
        if hasattr(mod, attr):
            delattr(mod, attr)


_MODS = ("ecentric_workspace.shell.server_nav", "ecentric_workspace.shell.api")


def setUpModule():
    _SAVED["frappe"] = sys.modules.get("frappe")
    sys.modules["frappe"] = T._fake_frappe()
    _forget(_MODS)


def tearDownModule():
    _forget(_MODS)
    if _SAVED.get("frappe") is None:
        sys.modules.pop("frappe", None)
    else:
        sys.modules["frappe"] = _SAVED["frappe"]


PAGE = ('<div class="grid"><aside class="ec-shell-mount" data-ec-shell="1" aria-label="n">'
        '<nav>old</nav></aside><main>body</main></div>')


def _render(route):
    _, _, sn = T._mods()
    return sn.rebuild_mount(PAGE, route)


def _sec(html):
    m = re.search(r'ec-shell-railbtn ec-shell-railon" href="[^"]*" data-ec-shell-rail="([a-z]+)"', html)
    return m.group(1) if m else None


def _panel_keys(html):
    panel = html.split('<div class="ec-shell-panel">', 1)[1]
    return re.findall(r'data-ec-shell-key="([^"]+)"', panel)


def _groups(html):
    return re.findall(r'class="ec-shell-grouplabel">([^<]*)<', html)


class TestRegistry(unittest.TestCase):

    def test_rail_is_valid_and_covers_every_context(self):
        _, shell_nav, _ = T._mods()
        self.assertTrue(shell_nav.validate_rail())
        owned = [c for s in shell_nav.RAIL for c in s["contexts"]]
        self.assertEqual(sorted(owned), sorted(c for c in shell_nav.CONTEXTS if c != "home"))

    def test_validator_rejects_bad_specs(self):
        _, shell_nav, _ = T._mods()
        base = [dict(s) for s in shell_nav.RAIL]
        bad_key = [dict(s) for s in base]
        bad_key[0] = dict(bad_key[0], keys=["home.portal.khong-co"])
        with self.assertRaises(ValueError):
            shell_nav.validate_rail(bad_key)
        dup_ctx = [dict(s) for s in base]
        dup_ctx[0] = dict(dup_ctx[0], contexts=["pm"])
        with self.assertRaises(ValueError):
            shell_nav.validate_rail(dup_ctx)
        orphan = [dict(s, contexts=[c for c in s["contexts"] if c != "hr"]) for s in base]
        with self.assertRaises(ValueError):
            shell_nav.validate_rail(orphan)

    def test_eight_sections_in_po_order(self):
        _, shell_nav, _ = T._mods()
        self.assertEqual([s["label"] for s in shell_nav.RAIL],
                         ["Trang chủ", "Bảng tin", "Chat", "Phê duyệt", "Công việc",
                          "Nhân sự", "Báo cáo", "Công ty"])


class TestServerRender(unittest.TestCase):

    def setUp(self):
        import frappe
        frappe.conf.clear()

    def test_route_lights_the_right_section(self):
        want = {"/": "home", "/home": "home", "/viec-cua-toi": "home", "/bang-tin": "feed",
                "/tin-noi-bo": "feed", "/chat": "chat", "/approvals": "approvals",
                "/mso-plan-form": "approvals", "/pm": "work", "/ec-hr/leave": "hr", "/sla": "hr",
                "/reports": "reports", "/alerts/rules": "reports", "/pnl-dashboard": "reports",
                "/tai-lieu": "company", "/gop-y": "company", "/hall": "company",
                "/ai-tool": "company", "/khao-sat": "company"}
        for route, sec in sorted(want.items()):
            self.assertEqual(_sec(_render(route)), sec, route)

    def test_portal_sections_show_only_their_own_items(self):
        self.assertEqual(_panel_keys(_render("/")), ["home.portal.home", "home.portal.overview"])
        self.assertEqual(_panel_keys(_render("/tin-noi-bo")), ["home.portal.feed", "home.portal.news"])
        self.assertEqual(_panel_keys(_render("/chat")), ["home.portal.chat"])
        co = _panel_keys(_render("/tai-lieu"))
        self.assertEqual(co[0], "home.portal.iso_docs")
        self.assertIn("home.portal.feedback", co)
        self.assertNotIn("home.portal.approvals", co, "khu Cong ty khong mang muc khu khac")
        self.assertEqual(_groups(_render("/tai-lieu")), [], "cot portal khong nhan nhom")

    def test_approvals_shows_mso_so_po_right_under_approvals(self):
        html = _render("/approvals")
        keys = _panel_keys(html)
        for k in ("legacy.create_mso", "legacy.create_so", "legacy.create_po"):
            self.assertIn(k, keys)
        self.assertEqual(_groups(html)[:3], ["Phê duyệt", "Tạo mới", "Chứng từ"])
        self.assertNotIn("core.home", keys, "Trang chu da nam tren thanh")
        self.assertIn('data-ec-shell-badge="action_center.approvals"', html.split("ec-shell-panel")[0],
                      "huy hieu phe duyet nam tren thanh")

    def test_module_section_appends_missing_portal_items_once(self):
        keys = _panel_keys(_render("/alerts/rules"))
        self.assertEqual(keys[:5], ["alerts.dashboard", "alerts.policies", "alerts.rules",
                                    "alerts.locks", "alerts.health"])
        self.assertEqual(keys[5:], ["home.portal.reports", "home.portal.weekly", "home.portal.pulse"],
                         "/alerts da co trong cot -> khong lap Alert Center")
        rep = _panel_keys(_render("/reports"))
        self.assertNotIn("home.portal.reports", rep, "cung route voi reporting.hub -> khong lap")
        self.assertIn("home.portal.alerts", rep)

    def test_mount_attrs_and_idempotent(self):
        _, _, sn = T._mods()
        once = _render("/approvals")
        tag = re.search(r'<aside[^>]*>', once).group(0)
        self.assertIn('data-ec-rail="1"', tag)
        self.assertIn('data-ec-nav-sig="approval_document@approvals|', tag)
        self.assertEqual(sn.rebuild_mount(once, "/approvals"), once)


class TestKillSwitch(unittest.TestCase):

    def tearDown(self):
        import frappe
        frappe.conf.clear()

    def test_flag_restores_the_one_column_menu(self):
        import frappe
        fb, shell_nav, sn = T._mods()
        rail_html = _render("/ec-hr/attendance")
        frappe.conf[shell_nav.RAIL_DISABLED_FLAG] = 1
        old = sn.rebuild_mount(rail_html, "/ec-hr/attendance")   # trang da co rail -> ve lai 1 cot
        tag = re.search(r'<aside[^>]*>', old).group(0)
        self.assertNotIn("data-ec-rail", tag)
        self.assertNotIn("ec-shell-rail", old)
        items = shell_nav.compose("hr")
        inner = old[old.index(">", old.index(sn.MOUNT_OPEN)) + 1:old.index(sn.MOUNT_CLOSE)]
        self.assertEqual(inner, fb.mount_inner_html(items, fb.match_active(items, "/ec-hr/attendance"),
                                                    live=True))

    def test_boot_carries_rail_by_the_same_switch(self):
        import frappe
        _, shell_nav, sn = T._mods()
        self.assertTrue(sn.rail_enabled())
        frappe.conf[shell_nav.RAIL_DISABLED_FLAG] = 1
        self.assertFalse(sn.rail_enabled())
        from ecentric_workspace.shell import api
        self.assertFalse(api._rail_on())


class TestJsParity(unittest.TestCase):
    ROUTES = ["/", "/tin-noi-bo", "/chat", "/viec-cua-toi", "/approvals", "/mso-plan-form",
              "/ec-hr/leave", "/reports", "/alerts/rules", "/pnl-dashboard", "/tai-lieu",
              "/ai-tool", "/ai-content/brand", "/khao-sat", "/hall", "/zz-khong-co"]

    def test_rail_view_and_markup_identical_in_js(self):
        node, why = T._node_ok()
        if not node:
            self.skipTest(why)
        fb, shell_nav, sn = T._mods()
        from ecentric_workspace.shell import api
        rail = shell_nav.rail_spec()
        home = shell_nav.compose("home")
        cases, want = [], {}
        for route in self.ROUTES:
            ctx = shell_nav.resolve_context(route)
            items = shell_nav.compose(ctx)
            sec, panel = fb.rail_view(rail, ctx, items, home, route)
            active = fb.match_active(panel, route)
            cases.append({"name": route, "path": route, "context": ctx,
                          "items": [api._ser(it) for it in items]})
            want[route] = {"sec": sec["key"] if sec else "", "keys": [it["key"] for it in panel],
                           "rail": fb.rail_html(rail, sec["key"] if sec else None),
                           "nav": fb.render_nav(panel, active, live=True),
                           "sig": sn.nav_signature(sn.sig_context(ctx, sec), panel, active)}
        rows = T._run_harness(node, "rail", {"rail": rail, "home": [api._ser(it) for it in home],
                                             "cases": cases})
        self.assertEqual(len(rows), len(self.ROUTES))
        for row in rows:
            w = want[row["name"]]
            for k in ("sec", "keys", "rail", "nav", "sig"):
                self.assertEqual(row[k], w[k], "%s %s" % (row["name"], k))


class TestHydration(unittest.TestCase):

    def _boot(self, rail=True):
        b = T.TestHydration._boot(T.TestHydration())
        if not rail:
            b["rail"] = None
        return b

    def _go(self, html, path, boot):
        node, why = T._node_ok(need_jsdom=True)
        if not node:
            self.skipTest(why)
        return T._run_harness(node, "hydrate", {"html": html, "pathname": path, "boot": boot})

    def test_server_rail_is_kept_on_every_section(self):
        for route in ("/", "/tin-noi-bo", "/approvals", "/ec-hr/leave", "/alerts/rules", "/tai-lieu", "/hall"):
            r = self._go(_render(route), route, self._boot())
            self.assertTrue(r["navKept"], route)
            self.assertEqual(r["rail"], "1", route)
            self.assertEqual(r["railBtns"], 8, route)
            self.assertEqual(r["username"], "Hoan Tran", route)

    def test_kill_switch_in_boot_repaints_one_column_and_drops_attr(self):
        r = self._go(_render("/approvals"), "/approvals", self._boot(rail=False))
        self.assertFalse(r["navKept"])
        self.assertIsNone(r["rail"])
        self.assertEqual(r["railBtns"], 0)

    def test_old_page_without_rail_gets_rail_from_boot(self):
        fb, _, _ = T._mods()
        baked = ('<aside class="ec-shell-mount" data-ec-shell="1" aria-label="n">%s</aside>'
                 % fb.render_mount_inner("/approvals"))
        r = self._go(baked, "/approvals", self._boot())
        self.assertEqual(r["rail"], "1")
        self.assertEqual(r["railOn"], "approvals")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (TestRegistry, TestServerRender, TestKillSwitch, TestJsParity, TestHydration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    if suite.countTestCases() != EXPECT_TOTAL:
        raise AssertionError("EXPECT_TOTAL=%d nhung nap %d test" % (EXPECT_TOTAL, suite.countTestCases()))
    return suite
