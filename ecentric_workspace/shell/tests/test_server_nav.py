# Copyright (c) 2026, eCentric and contributors
"""Menu chung do SERVER dung luc render (shell/server_nav.py) -- A65 / NHIEU_LOP GD 1.1.

Khoa 4 dieu:
1. Hook chi thay DUNG vung `.ec-shell-mount`, moi byte khac cua trang giu nguyen;
   trang khong thuoc dien (0 / 2 mount, khong opt-in, long aside, khong dong) de nguyen.
2. Ngu canh server chon la ngu canh THIET KE (co tinh muc sidebar_hidden) -- chot loi
   /viec-cua-toi bi ve menu Phe duyet.
3. Ban dung SONG (live) giong HET ban JS ve (navHtml / navSig), nen client giu nguyen
   DOM server khi chu ky trung -- khong ve lai menu.
4. Ban tinh (`regenerate` nuong vao file repo) KHONG doi: cong vo shell khong troi.

Chay:  python3 -m unittest ecentric_workspace.shell.tests.test_server_nav
Phan JS can `node` (+ `jsdom` cho phan hydrate). Thieu thi test do SKIP kem ly do --
skip khong phai xanh; bao cao cuoi in ro bao nhieu test da chay that.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

HARNESS = os.path.join(HERE, "server_nav_harness.js")
HUB_PAGE = os.path.join(APP, "approval_center", "ui", "hub", "main_section.html")

#: So test trong file. Lech voi so test thuc chay = co test bi bo sot / khong nap.
EXPECT_TOTAL = 21

_SAVED = {}


def _fake_frappe():
    fake = types.ModuleType("frappe")
    fake.conf = {}
    fake.local = types.SimpleNamespace(request=None)
    fake.logged = []

    def log_error(title=None, **kw):
        fake.logged.append(title)
    fake.log_error = log_error

    class _Cache(object):
        def __init__(self):
            self.d = {}

        def get_value(self, k):
            return self.d.get(k)

        def set_value(self, k, v, expires_in_sec=None):
            self.d[k] = v
    fake._cache = _Cache()
    fake.cache = lambda: fake._cache
    fake._ = lambda s: s
    fake.whitelist = lambda *a, **k: (lambda f: f)
    return fake


def setUpModule():
    for name in ("frappe", "ecentric_workspace.shell.server_nav", "ecentric_workspace.shell.api"):
        _SAVED[name] = sys.modules.get(name)
    sys.modules["frappe"] = _fake_frappe()
    for name in ("ecentric_workspace.shell.server_nav", "ecentric_workspace.shell.api"):
        sys.modules.pop(name, None)


def tearDownModule():
    for name, mod in _SAVED.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _mods():
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import nav as shell_nav
    from ecentric_workspace.shell import server_nav as sn
    return fb, shell_nav, sn


def _hub():
    with io.open(HUB_PAGE, encoding="utf-8") as f:
        return f.read()


def _mount_span(ms, sn):
    i = ms.index(sn.MOUNT_OPEN)
    return i, ms.index(">", i), ms.index(sn.MOUNT_CLOSE, i)


class TestSignature(unittest.TestCase):

    def test_signature_is_context_active_and_keys_in_render_order(self):
        _, _, sn = _mods()
        items = [{"key": "a"}, {"key": "p", "children": [{"key": "c1"}, {"key": "c2"}]}, {"key": "b"}]
        self.assertEqual(sn.nav_signature("hr", items, "c2"), "hr|c2|a,p,c1,c2,b")
        self.assertEqual(sn.nav_signature(None, [], None), "||")


class TestRebuildMount(unittest.TestCase):

    def test_only_the_mount_region_changes(self):
        _, _, sn = _mods()
        ms = _hub()
        new = sn.rebuild_mount(ms, "/approvals")
        i, _, j = _mount_span(ms, sn)
        i2, _, j2 = _mount_span(new, sn)
        self.assertEqual(ms[:i], new[:i2], "bytes BEFORE the mount must be untouched")
        self.assertEqual(ms[j:], new[j2:], "bytes AFTER the mount must be untouched")

    def test_open_tag_declares_context_and_signature_once(self):
        _, _, sn = _mods()
        new = sn.rebuild_mount(_hub(), "/approvals")
        i, t, _ = _mount_span(new, sn)
        tag = new[i:t + 1]
        self.assertEqual(tag.count('data-ec-context="approval_document"'), 1)
        self.assertEqual(tag.count("data-ec-nav-sig="), 1)
        self.assertIn('data-ec-shell="1"', tag)

    def test_idempotent(self):
        _, _, sn = _mods()
        once = sn.rebuild_mount(_hub(), "/approvals")
        self.assertEqual(sn.rebuild_mount(once, "/approvals"), once)

    def test_inner_is_the_live_render_of_the_resolved_context(self):
        fb, shell_nav, sn = _mods()
        new = sn.rebuild_mount(_hub(), "/ec-hr/attendance")
        _, t, j = _mount_span(new, sn)
        items = shell_nav.compose("hr")
        # Menu 2 tang (07/10/2026, mac dinh bat): cot = rail_view() cua ngu canh; menu 1 cot cu
        # (kill switch) duoc khoa o test_shell_rail.TestKillSwitch.
        rail = shell_nav.rail_spec()
        sec, panel, blocks, active, _ = sn.rail_parts(rail, "hr", items, "/ec-hr/attendance")
        self.assertEqual(new[t + 1:j], fb.mount_inner_html(panel, active, live=True, rail=rail, section=sec,
                                                           blocks=blocks))
        self.assertNotIn("ec-shell-fallback", new[t + 1:j])
        self.assertIn("data-ec-shell-key=", new[t + 1:j])

    def test_design_context_per_route(self):
        _, _, sn = _mods()
        want = {"/viec-cua-toi": "home", "/pnl-dashboard": "pnl", "/ec-hr/attendance": "hr",
                "/approvals": "approval_document", "/home": "home", "/ai-tool": "ai_tools"}
        for route, ctx in sorted(want.items()):
            new = sn.rebuild_mount(_hub(), route)
            i, t, _ = _mount_span(new, sn)
            self.assertIn('data-ec-context="%s"' % ctx, new[i:t + 1], route)


class TestRebuildGuards(unittest.TestCase):
    OK = '<div id="x"><aside class="ec-shell-mount" data-ec-shell="1" aria-label="n"></aside><p>body</p></div>'

    def test_no_mount_is_left_alone(self):
        _, _, sn = _mods()
        self.assertIsNone(sn.rebuild_mount("<div>no shell here</div>", "/approvals"))
        self.assertIsNotNone(sn.rebuild_mount(self.OK, "/approvals"))

    def test_two_mounts_are_left_alone(self):
        _, _, sn = _mods()
        self.assertIsNone(sn.rebuild_mount(self.OK + self.OK, "/approvals"))

    def test_mount_without_opt_in_is_left_alone(self):
        _, _, sn = _mods()
        self.assertIsNone(sn.rebuild_mount(self.OK.replace(' data-ec-shell="1"', ""), "/approvals"))

    def test_nested_or_unclosed_aside_is_left_alone(self):
        _, _, sn = _mods()
        nested = self.OK.replace('aria-label="n">', 'aria-label="n"><aside>x</aside>')
        self.assertIsNone(sn.rebuild_mount(nested, "/approvals"))
        self.assertIsNone(sn.rebuild_mount(self.OK.replace("</aside>", ""), "/approvals"))


class TestHook(unittest.TestCase):

    def setUp(self):
        import frappe
        frappe.conf.clear()
        frappe.logged[:] = []
        frappe._cache.d.clear()

    def test_kill_switch(self):
        import frappe
        _, _, sn = _mods()
        frappe.conf[sn.KILL_SWITCH] = 1
        self.assertIsNone(sn.fill_shell_mount({"main_section": _hub(), "route": "approvals"}))

    def test_pages_without_main_section_are_ignored(self):
        _, _, sn = _mods()
        self.assertIsNone(sn.fill_shell_mount({}))
        self.assertIsNone(sn.fill_shell_mount({"main_section": None, "route": "login"}))
        self.assertIsNone(sn.fill_shell_mount({"main_section": "<p>plain</p>", "route": "x"}))

    def test_happy_path_uses_the_web_page_route(self):
        _, _, sn = _mods()
        out = sn.fill_shell_mount({"main_section": _hub(), "route": "viec-cua-toi"})
        self.assertIn('data-ec-context="home"', out["main_section"])

    def test_failure_never_raises_and_logs_once(self):
        import frappe
        _, _, sn = _mods()
        orig = sn.rebuild_mount
        try:
            sn.rebuild_mount = lambda ms, route: 1 / 0
            self.assertIsNone(sn.fill_shell_mount({"main_section": _hub(), "route": "approvals"}))
            self.assertIsNone(sn.fill_shell_mount({"main_section": _hub(), "route": "approvals"}))
        finally:
            sn.rebuild_mount = orig
        self.assertEqual(frappe.logged, [sn.LOG_TITLE])


class TestStaticFallbackUnchanged(unittest.TestCase):

    def test_default_render_is_the_old_static_markup(self):
        fb, _, _ = _mods()
        html = fb.render_mount_inner("/approvals")
        self.assertIn('class="ec-shell-nav ec-shell-fallback"', html)
        self.assertNotIn("data-ec-shell-key", html)
        self.assertNotIn("data-ec-shell-badge", html)


def _node_ok(need_jsdom=False):
    node = shutil.which("node")
    if not node:
        return None, "khong co `node` tren PATH"
    if need_jsdom:
        rc = subprocess.run([node, "-e", "require('jsdom')"], capture_output=True, cwd=HERE)
        if rc.returncode != 0:
            return None, "khong nap duoc `jsdom` (NODE_PATH?)"
    return node, ""


def _run_harness(node, mode, fixture):
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with io.open(fd, "w", encoding="utf-8") as f:
            json.dump(fixture, f, ensure_ascii=False)
        rc = subprocess.run([node, HARNESS, mode, path], capture_output=True, cwd=HERE)
        if rc.returncode != 0:
            raise AssertionError("harness %s loi: %s" % (mode, rc.stderr.decode("utf-8", "replace")))
        return json.loads(rc.stdout.decode("utf-8"))
    finally:
        os.remove(path)


class TestJsParity(unittest.TestCase):
    ROUTES = {"home": "/home", "approval_document": "/approvals", "hr": "/ec-hr/attendance",
              "alert_center": "/alerts", "reporting": "/reports", "pnl": "/pnl-dashboard",
              "pm": "/pm", "ai_tools": "/ai-tool"}

    def _cases(self):
        fb, shell_nav, sn = _mods()
        from ecentric_workspace.shell import api
        cases, want = [], {}
        for ctx, route in sorted(self.ROUTES.items()):
            items = shell_nav.compose(ctx)
            active = fb.match_active(items, route)
            cases.append({"name": ctx, "context": ctx, "active": active,
                          "items": [api._ser(it) for it in items]})
            want[ctx] = (fb.render_nav(items, active, live=True), sn.nav_signature(ctx, items, active))
        return cases, want

    def test_live_nav_markup_is_byte_identical_to_js(self):
        node, why = _node_ok()
        if not node:
            self.skipTest(why)
        cases, want = self._cases()
        for row in _run_harness(node, "parity", {"cases": cases}):
            self.assertEqual(row["html"], want[row["name"]][0], row["name"])

    def test_signature_formula_is_identical_in_js(self):
        node, why = _node_ok()
        if not node:
            self.skipTest(why)
        cases, want = self._cases()
        for row in _run_harness(node, "parity", {"cases": cases}):
            self.assertEqual(row["sig"], want[row["name"]][1], row["name"])


class TestHydration(unittest.TestCase):
    """ec_shell.js THAT trong jsdom, tren trang server da dung menu."""

    def _boot(self, extra_role_item=None):
        from ecentric_workspace.shell import api
        _, shell_nav, _ = _mods()
        contexts = {}
        for name in shell_nav.CONTEXTS:
            items = [api._ser(it) for it in shell_nav.compose(name)]
            if extra_role_item and name == extra_role_item[0]:
                items.append(extra_role_item[1])
            contexts[name] = {"items": items, "entry": None}
        return {"enabled": True, "nav": contexts[shell_nav.DEFAULT_CONTEXT]["items"],
                "contexts": contexts, "context_order": list(shell_nav.CONTEXT_ORDER),
                "default_context": shell_nav.DEFAULT_CONTEXT, "all_items": [],
                "user": {"name": "hoan@x.vn", "full_name": "Hoan Tran", "image": ""},
                "rail": shell_nav.rail_spec()}

    def _page(self, route):
        _, _, sn = _mods()
        return sn.rebuild_mount(_hub(), route)

    def _go(self, html, pathname, boot):
        node, why = _node_ok(need_jsdom=True)
        if not node:
            self.skipTest(why)
        return _run_harness(node, "hydrate", {"html": html, "pathname": pathname, "boot": boot})

    def test_matching_menu_is_kept_and_only_the_user_card_changes(self):
        page = self._page("/approvals")
        sig = re.search(r'data-ec-nav-sig="([^"]*)"', page).group(1)
        r = self._go(page, "/approvals", self._boot())
        self.assertTrue(r["navKept"], "server-rendered <nav> must NOT be repainted")
        self.assertEqual(r["sig"], sig)
        self.assertEqual(r["username"], "Hoan Tran")
        self.assertEqual(r["logout"], 1)

    def test_viec_cua_toi_keeps_the_portal_menu(self):
        r = self._go(self._page("/viec-cua-toi"), "/viec-cua-toi", self._boot())
        self.assertEqual(r["ctx"], "home", "client must trust the server context, not guess approval")
        self.assertTrue(r["navKept"])

    def test_role_gated_item_repaints_and_restamps(self):
        extra = ("approval_document", {"key": "zz.role.only", "label": "Role only", "route": "/zz-role",
                                       "icon": "doc", "group": "Zzz", "active_patterns": ["/zz-role"],
                                       "keywords": [], "no_prerender": False, "soon": False,
                                       "alias": False, "badge_source": "", "children": []})
        page = self._page("/approvals")
        before = re.search(r'data-ec-nav-sig="([^"]*)"', page).group(1)
        r = self._go(page, "/approvals", self._boot(extra_role_item=extra))
        self.assertFalse(r["navKept"], "a different item set must repaint")
        self.assertNotEqual(r["sig"], before)
        self.assertTrue(r["sig"].endswith(",zz.role.only"))

    def test_old_baked_mount_without_signature_still_hydrates(self):
        fb, _, _ = _mods()
        baked = ('<aside class="ec-shell-mount" data-ec-shell="1" aria-label="n">%s</aside>'
                 % fb.render_mount_inner("/approvals"))
        r = self._go(baked, "/approvals", self._boot())
        self.assertFalse(r["navKept"], "no server signature -> old behaviour (full client render)")
        self.assertEqual(r["username"], "Hoan Tran")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (TestSignature, TestRebuildMount, TestRebuildGuards, TestHook,
                 TestStaticFallbackUnchanged, TestJsParity, TestHydration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    if suite.countTestCases() != EXPECT_TOTAL:
        raise AssertionError("EXPECT_TOTAL=%d nhung nap %d test" % (EXPECT_TOTAL, suite.countTestCases()))
    return suite
