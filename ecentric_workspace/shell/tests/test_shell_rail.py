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
EXPECT_TOTAL = 32

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


FOOT = '<div class="ec-shell-foot"><a class="ec-shell-usercard" href="/app/user">x</a></div>'

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
        self.assertEqual(_panel_keys(_render("/")), ["rail.home.mywork", "home.portal.home", "home.portal.overview",
                                                     "rail.home.att", "rail.home.leave", "rail.home.req", "rail.help"])
        self.assertEqual(_panel_keys(_render("/tin-noi-bo")), ["home.portal.feed", "rail.feed.clubs",
                                                               "home.portal.news", "rail.feed.post"],
                         "nguoi chua chung minh quyen (render chung) khong thay Viet tin / Quan ly")
        co = _panel_keys(_render("/tai-lieu"))
        self.assertEqual(co[0], "home.portal.iso_docs")
        self.assertIn("home.portal.feedback", co)
        self.assertNotIn("home.portal.approvals", co, "khu Cong ty khong mang muc khu khac")
        self.assertEqual(_groups(_render("/tai-lieu")), ["Tài liệu", "Tiếng nói nhân viên", "Công cụ", "Khác"])

    def test_approvals_column_has_two_clear_parts(self):
        html = _render("/approvals")
        nav = html.split('<nav class="ec-shell-nav"', 1)[1]
        parts = re.findall(r'<div class="ec-shell-part">([^<]+)</div>', nav)
        self.assertEqual(parts, ["Yêu cầu phê duyệt", "Chứng từ MSO · SO · PO"])
        first, second = nav.split('class="ec-shell-part">Chứng từ', 1)
        for k in ("rail.appr.waiting", "rail.appr.sent", "apc.catalog", "apc.all", "apc.dashboard"):
            self.assertIn('data-ec-shell-key="%s"' % k, first, k)
        for k in ("legacy.create_mso", "legacy.create_so", "legacy.create_po", "approval.inbox", "tickets.all"):
            self.assertIn('data-ec-shell-key="%s"' % k, second, k)
            self.assertNotIn('data-ec-shell-key="%s"' % k, first, k)
        chips = re.search(r'<div class="ec-shell-chips">(.*?)</div>', second).group(1)
        self.assertEqual(re.findall(r'>([^<]+)</a>', chips), ["MSO", "SO", "PO"])
        self.assertEqual(_sec(_render("/mso-plan-form")), "approvals", "thanh van GOP mot khu")

    def test_reports_section_has_pnl_and_alerts_as_submenus(self):
        html = _render("/alerts/rules")
        self.assertIn('data-ec-shell-subtoggle="rail.rep.alerts" aria-expanded="true"', html, "dang o trong -> mo")
        self.assertIn('data-ec-shell-subtoggle="rail.rep.pnl" aria-expanded="false"', html, "khac -> gap")
        self.assertIn('<div class="ec-shell-children" hidden data-ec-shell-children="rail.rep.pnl">', html)
        self.assertIn('data-ec-shell-key="alerts.rules" aria-current="page"', html)
        self.assertIn(">Quy tắc<", html)

    def test_mount_attrs_and_idempotent(self):
        _, _, sn = T._mods()
        once = _render("/approvals")
        tag = re.search(r'<aside[^>]*>', once).group(0)
        self.assertIn('data-ec-rail="1"', tag)
        self.assertIn('data-ec-nav-sig="approval_document@approvals|', tag)
        self.assertEqual(sn.rebuild_mount(once, "/approvals"), once)


class TestRound2(unittest.TestCase):
    """Vong sua 07/10 (PO chup): the nguoi dung xuong day thanh, Chat khong cot, nhan ngan."""

    def setUp(self):
        import frappe
        frappe.conf.clear()

    def test_user_card_sits_at_the_bottom_of_the_rail(self):
        html = _render("/approvals")
        rail, panel = html.split('<div class="ec-shell-panel">', 1)
        self.assertIn('class="ec-shell-railsp"></span><div class="ec-shell-foot">', rail)
        self.assertNotIn("ec-shell-foot", panel)

    def test_chat_has_no_panel_others_do(self):
        tag = re.search(r'<aside[^>]*>', _render("/chat")).group(0)
        self.assertIn('data-ec-nopanel="1"', tag)
        for route in ("/", "/approvals", "/tin-noi-bo"):
            self.assertNotIn("data-ec-nopanel", re.search(r'<aside[^>]*>', _render(route)).group(0), route)

    def test_switching_away_from_chat_drops_nopanel(self):
        _, _, sn = T._mods()
        chat = _render("/chat")
        again = sn.rebuild_mount(chat, "/approvals")
        self.assertNotIn("data-ec-nopanel", re.search(r'<aside[^>]*>', again).group(0))

    def test_install_guide_is_a_small_footer_link(self):
        html = _render("/ec-hr/attendance")
        nav, foot = html.split('<div class="ec-shell-panel">', 1)[1].split("</nav>", 1)
        self.assertNotIn("hr.install_guide", nav)
        self.assertIn('<a class="ec-shell-help" href="/ec-hr/huong-dan-cai-app" data-ec-shell-key="hr.install_guide">',
                      foot)

    def test_css_fixes_present(self):
        import io
        import os
        css = io.open(os.path.join(T.APP, "public", "css", "ec_shell.bundle.css"), encoding="utf-8").read()
        self.assertIn(".ec-shell-rail a.ec-shell-railbtn", css, "do uu tien cao hon `.xxx a{color}` cua trang")
        self.assertIn('.ec-shell-mount[data-ec-rail="1"]{\n  width:var(--ec-shell-w,248px)', css)
        self.assertIn('.ec-shell-mount[data-ec-nopanel="1"] .ec-shell-panel{ display:none; }', css)
        chat = io.open(os.path.join(T.APP, "public", "css", "ec_chat_page.css"), encoding="utf-8").read()
        self.assertIn("grid-template-columns:auto minmax(0,1fr)", chat)


class TestLayout(unittest.TestCase):
    """Cot theo bo cuc (07/10/2026): khong mat muc, loc vai tro, menu con, link khong to dang chon."""

    def setUp(self):
        import frappe
        frappe.conf.clear()

    def test_every_module_item_is_placed_no_khac_group(self):
        for route in ("/", "/approvals", "/pm", "/ec-hr/attendance", "/reports", "/alerts", "/pnl-dashboard",
                      "/tai-lieu", "/ai-tool", "/khao-sat", "/bang-tin"):
            self.assertNotIn('grouplabel">Mục khác<', _render(route), route)

    def test_unplaced_module_item_falls_into_khac(self):
        fb, shell_nav, _ = T._mods()
        sec = [s for s in shell_nav.rail_spec() if s["key"] == "reports"][0]
        extra = {"key": "reporting.moi", "label": "Bao cao moi", "route": "/bao-cao-moi", "icon": "chart",
                 "group": "", "active_patterns": ["/bao-cao-moi"]}
        items = shell_nav.compose("reporting") + [extra]
        blocks, sig, _ = fb.rail_layout(sec, "reporting", items, fb.rail_pool([items]))
        self.assertEqual(blocks[-1]["label"], "Mục khác")
        self.assertEqual([i["key"] for i in blocks[-1]["items"]], ["reporting.moi"])

    def test_role_links_follow_the_viewer(self):
        _, shell_nav, _ = T._mods()

        def keys(roles, sec):
            lay = [s for s in shell_nav.rail_spec(roles) if s["key"] == sec][0]["layout"]
            out = []
            for b in lay:
                for i in (b.get("items") or []) + ([b["item"]] if b.get("item") else []):
                    out.append(i["key"])
                    out += [c["key"] for c in i.get("children") or []]
            return out
        self.assertNotIn("rail.feed.write", keys(None, "feed"))
        self.assertNotIn("rail.feed.write", keys(["Employee"], "feed"))
        self.assertIn("rail.feed.write", keys(["HR User"], "feed"))
        self.assertIn("rail.co.docsmg", keys(["Ban ISO"], "company"))
        self.assertNotIn("rail.co.docsmg", keys(["HR User"], "company"))

    def test_single_child_tree_becomes_plain_link(self):
        html = _render("/tai-lieu")
        self.assertNotIn('data-ec-shell-subtoggle="home.portal.iso_docs"', html, "nhan vien: 1 muc con -> bam thang")
        self.assertIn('data-ec-shell-key="home.portal.iso_docs" aria-current="page"', html)
        self.assertIn('data-ec-shell-subtoggle="ai_tools.hub"', html, "SI Tool van co menu con")

    def test_query_links_never_steal_the_highlight(self):
        html = _render("/approvals/all-requests")
        self.assertIn('data-ec-shell-key="apc.all" aria-current="page"', html)
        self.assertNotIn('data-ec-shell-key="rail.appr.waiting" aria-current', html)

    def test_badges_reuse_existing_sources(self):
        self.assertIn('data-ec-shell-reminder-badge="1" hidden', _render("/").split('<div class="ec-shell-panel">')[1])
        self.assertIn('data-ec-shell-key="rail.appr.waiting"><svg', _render("/approvals"))
        appr = _render("/approvals").split('<div class="ec-shell-panel">')[1]
        self.assertIn('data-ec-shell-badge="action_center.approvals" hidden', appr)


class TestCollapse(unittest.TestCase):
    """Nut thu gon cot (07/10/2026): co nut o dau cot + nut mo lai tren thanh; CSS doi luoi trang."""

    def setUp(self):
        import frappe
        frappe.conf.clear()

    def test_buttons_rendered(self):
        html = _render("/approvals")
        rail, panel = html.split('<div class="ec-shell-panel">', 1)
        self.assertIn('data-ec-shell-collapse="0"', rail, "nut mo lai nam tren thanh")
        self.assertIn('<span class="ec-shell-paneltitle">Phê duyệt</span><button type="button" class="ec-shell-collapse" '
                      'data-ec-shell-collapse="1"', panel)

    def test_css_shrinks_page_grid_and_pm(self):
        import io
        import os
        css = io.open(os.path.join(T.APP, "public", "css", "ec_shell.bundle.css"), encoding="utf-8").read()
        self.assertIn('[data-ec-shell-collapsed="1"] :has(> .ec-shell-mount[data-ec-rail="1"]){ grid-template-columns:62px', css)
        self.assertIn('[data-ec-shell-collapsed="1"] #ec-pm-root{ grid-template-columns:62px', css,
                      "/pm co !important rieng (#ec-pm-root) -> can quy tac cu the hon")
        self.assertIn('[data-ec-shell-collapsed="1"] .ec-shell-mount[data-ec-rail="1"] .ec-shell-panel{ display:none; }', css)


class TestPageIsolationCss(unittest.TestCase):
    """10/10/2026: khoi #ec-reporting-shell-isolation (/weekly-update, /team-pulse) ep
    .ec-shell-mount{flex-direction:column;width:auto} bang !important -> thanh bi day len dau cot.
    Vo shell phai thang: quy tac rail mode cung !important, do uu tien cao hon."""

    def test_rail_mode_wins_over_page_important_rules(self):
        import io
        import os
        css = io.open(os.path.join(T.APP, "public", "css", "ec_shell.bundle.css"), encoding="utf-8").read()
        rule = css[css.index('.ec-shell-mount[data-ec-rail="1"]{\n  flex-direction:row !important'):]
        self.assertIn("width:var(--ec-shell-w,248px) !important", rule[:300])
        self.assertIn('[data-ec-shell-collapsed="1"] .ec-shell-mount[data-ec-rail="1"]{\n  width:var(--ec-rail-w) !important',
                      css)
        self.assertIn('.ec-shell-mount[data-ec-rail="1"] .ec-shell-panel a.ec-shell-item.ec-shell-active{\n  '
                      'background:var(--ec-navy) !important', css)


class TestPmPatch(unittest.TestCase):
    """p272: dua /pm ve vo shell bang DUNG pm.pages.transform; khong nem trong migrate."""

    def _run(self, exists, ms, transform):
        import frappe
        from ecentric_workspace.approval_center.patches import p272_pm_vao_vo_shell as P
        from ecentric_workspace.pm import pages as PM
        saved = []

        class Doc(object):
            def save(self, ignore_permissions=False):
                saved.append((self.main_section, self.main_section_html))
        frappe.db = type("DB", (), {"exists": lambda self, dt, n: exists,
                                    "get_value": lambda self, dt, n, f: ms})()
        frappe.get_doc = lambda dt, n: Doc()
        frappe.get_traceback = lambda: "tb"
        frappe.logged[:] = []
        orig = PM.transform
        PM.transform = transform
        try:
            P.execute()
        finally:
            PM.transform = orig
        return saved, list(frappe.logged)

    def test_updates_unchanged_missing_and_never_raises(self):
        saved, log = self._run(True, "old", lambda ms: "new")
        self.assertEqual(saved, [("new", "new")])
        saved, log = self._run(True, "same", lambda ms: ms)
        self.assertEqual(saved, [])
        saved, log = self._run(False, "", lambda ms: "x")
        self.assertEqual(saved, [])

        def boom(ms):
            raise ValueError("PM rail not found")
        saved, log = self._run(True, "weird", boom)
        self.assertEqual(saved, [])
        self.assertIn("p272 pm vo shell FAILED", log)


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
    ROUTES = ["/", "/tin-noi-bo", "/bang-tin/cau-lac-bo", "/chat", "/viec-cua-toi", "/approvals",
              "/approvals/all-requests", "/mso-plan-form", "/ec-hr/leave", "/pm", "/reports", "/alerts/rules",
              "/pnl-dashboard", "/tai-lieu", "/gop-y", "/ai-tool", "/ai-content/ho-so-brand", "/khao-sat",
              "/hall", "/huong-dan", "/zz-khong-co"]

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
            sec, panel, blocks, active, sig = sn.rail_parts(rail, ctx, items, route)
            cases.append({"name": route, "path": route, "context": ctx,
                          "items": [api._ser(it) for it in items]})
            if blocks is not None:
                keys = sig.split("|", 2)[2].split(",")
                nav = fb.rail_panel_nav(blocks, active)
            else:
                keys = [it["key"] for it in panel]
                nav = fb.render_nav(panel, active, live=True)
            want[route] = {"sec": sec["key"] if sec else "", "keys": keys,
                           "rail": fb.rail_html(rail, sec["key"] if sec else None, FOOT),
                           "nav": nav, "sig": sig}
        contexts = {c: {"items": [api._ser(it) for it in shell_nav.compose(c)]} for c in shell_nav.CONTEXTS}
        rows = T._run_harness(node, "rail", {"rail": rail, "home": [api._ser(it) for it in home],
                                             "contexts": contexts, "cases": cases, "foot": FOOT})
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
            self.assertTrue(r["footInRail"], route)
            self.assertEqual(r["username"], "Hoan Tran", route)

    def test_open_submenu_closes_on_first_click(self):
        node, why = T._node_ok(need_jsdom=True)
        if not node:
            self.skipTest(why)
        r = T._run_harness(node, "hydrate", {"html": _render("/alerts/rules"), "pathname": "/alerts/rules",
                                             "boot": self._boot(), "click": "rail.rep.alerts"})
        self.assertTrue(r["navKept"])
        self.assertEqual(r["clicked"], {"expanded": "false", "hidden": True},
                         "server ve san o trang thai MO -> lan bam dau phai GAP")

    def test_collapse_button_toggles_and_remembers(self):
        node, why = T._node_ok(need_jsdom=True)
        if not node:
            self.skipTest(why)
        r = T._run_harness(node, "hydrate", {"html": _render("/approvals"), "pathname": "/approvals",
                                             "boot": self._boot(), "clickSel": ["[data-ec-shell-collapse='1']"]})
        self.assertEqual(r["collapsed"], {"attr": "1", "saved": "1"})
        r = T._run_harness(node, "hydrate", {"html": _render("/approvals"), "pathname": "/approvals",
                                             "boot": self._boot(),
                                             "clickSel": ["[data-ec-shell-collapse='1']", "[data-ec-shell-collapse='0']"]})
        self.assertEqual(r["collapsed"], {"attr": None, "saved": "0"})

    def test_chat_page_keeps_rail_without_panel(self):
        r = self._go(_render("/chat"), "/chat", self._boot())
        self.assertTrue(r["navKept"])
        self.assertEqual(r["nopanel"], "1")

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
    for case in (TestRegistry, TestServerRender, TestRound2, TestLayout, TestCollapse, TestPageIsolationCss, TestPmPatch, TestKillSwitch, TestJsParity,
                 TestHydration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    if suite.countTestCases() != EXPECT_TOTAL:
        raise AssertionError("EXPECT_TOTAL=%d nhung nap %d test" % (EXPECT_TOTAL, suite.countTestCases()))
    return suite
