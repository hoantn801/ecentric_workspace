# Copyright (c) 2026, eCentric and contributors
"""Homepage Sync Safety Hotfix contracts.

The rejected Daily Cockpit page is GONE from the sync path, and
sync_home_page performs ZERO writes while no approved baseline is pinned.
Runnable without a bench (frappe stubbed; any db/doc access explodes)."""
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)


class _Boom:
    """Any attribute access = attempted frappe/db interaction -> test failure."""
    def __getattr__(self, name):
        raise AssertionError("guarded sync must not touch frappe.%s" % name)


def _install_tripwire_frappe():
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda f: f)
    stub._ = lambda s: s
    # db / get_doc / throw etc. all trip:
    stub.db = _Boom()
    stub.get_doc = _Boom().__getattr__  # any call attempt raises
    stub.throw = lambda *a, **k: (_ for _ in ()).throw(AssertionError("frappe.throw in guarded path"))
    sys.modules["frappe"] = stub
    return stub


class TestHomeSyncGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = sys.modules.get("frappe")
        _install_tripwire_frappe()
        # page_sync imports page_sync_util which imports frappe -> stub first
        for m in ("ecentric_workspace.legacy_pages.home.page_sync",
                  "ecentric_workspace.approval_center.page_sync_util"):
            sys.modules.pop(m, None)
        cls.ps = importlib.import_module("ecentric_workspace.legacy_pages.home.page_sync")

    @classmethod
    def tearDownClass(cls):
        if cls._saved is not None:
            sys.modules["frappe"] = cls._saved

    def test_sentinel_is_unset(self):
        self.assertIsNone(self.ps.BASELINE_SHA256,
                          "no approved homepage baseline may be pinned yet")

    def test_sync_guard_state_contract(self):
        # frappe.db is a tripwire: ANY read/write raises AssertionError.
        # Pre-activation: sync() must complete without touching frappe.
        # Post-activation (ENABLE_SHELL_BOUNDARY=True): the boundary path
        # legitimately reads the live page, so the zero-interaction proof
        # applies to the BASELINE path remaining sentinel-guarded instead.
        if not self.ps.ENABLE_SHELL_BOUNDARY:
            res = self.ps.sync()
            self.assertEqual(res["action"], "guarded")
            self.assertIn("zero writes", res["reason"])
        else:
            import inspect
            src = inspect.getsource(self.ps.sync)
            self.assertIn('BASELINE_SHA256 is None', src)
            self.assertLess(src.index('"guarded"'), src.index("upsert_web_page"),
                            "baseline upsert stays behind the sentinel guard")

    def test_endpoint_cannot_upsert_cockpit_markup(self):
        # the rejected authored page is gone from the module directory...
        self.assertFalse(os.path.exists(self.ps._baseline_path()),
                         "rejected Cockpit main_section.html must be deleted")
        # ...the boundary transform ACTIVELY refuses cockpit input...
        with self.assertRaises(ValueError):
            self.ps.transform_home("<div class='ec-ck'>cockpit"
                                   "<a data-ec-notification-bell=\"1\"></a></div>")
        # ...and an explicit html argument can never reach a write while the
        # baseline sentinel is unset (boundary path ignores the argument).
        import inspect
        branch = inspect.getsource(self.ps.sync)
        boundary = branch[branch.index("ENABLE_SHELL_BOUNDARY"):branch.index("BASELINE_SHA256 is None")]
        self.assertNotIn("upsert_web_page", boundary)

    def test_upsert_unreachable_while_guarded(self):
        import inspect
        src = inspect.getsource(self.ps.sync)
        # the guard returns BEFORE any upsert_web_page reference
        self.assertLess(src.index('"guarded"'), src.index("upsert_web_page"))
        self.assertIn("BASELINE_SHA256 is None", src)

    def test_no_static_serving_and_no_website_settings(self):
        src = inspect_src = open(os.path.join(APP, "legacy_pages", "home", "page_sync.py"),
                                 encoding="utf-8").read()
        self.assertNotIn("ensure_static_serving", src, "home stays dynamic (live Jinja)")
        self.assertNotIn('"Website Settings"', src)

    def test_sm_gate_kept(self):
        src = open(os.path.join(APP, "legacy_pages", "home", "page_sync.py"),
                   encoding="utf-8").read()
        self.assertIn("System Manager", src)


class TestCockpitRetired(unittest.TestCase):
    def test_no_cockpit_markup_in_repo_sync_path(self):
        home = os.path.join(APP, "legacy_pages", "home")
        for fname in os.listdir(home):
            if fname.endswith((".html",)):
                self.fail("no authored homepage HTML may exist while guarded: " + fname)
        ps = open(os.path.join(home, "page_sync.py"), encoding="utf-8").read()
        # cockpit markup may only appear inside the REFUSAL guard strings; no
        # authored cockpit markup (class definitions / injected scripts) may
        # exist in the sync path.
        for marker in ('class="ec-ck', "ec-ck-grid", "ck-attn",
                       "data-ec-shell-quickaccess", "_with_live_chatbot"):
            self.assertNotIn(marker, ps, marker)
        self.assertIn("rejected Cockpit markup detected", ps,
                      "transform must actively REFUSE cockpit input")

    def test_action_provider_backend_intact(self):
        api = open(os.path.join(APP, "action_center", "api.py"), encoding="utf-8").read()
        for keep in ("def get_action_items", "def get_my_requests_summary"):
            self.assertIn(keep, api, keep)
        # classification/due logic moved to the shared feed service (1a)
        feed = open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        for keep in ("def build_feed", "def classify", "counts[bucket] += 1"):
            self.assertIn(keep, feed, keep)
        res = open(os.path.join(APP, "action_center", "resolvers.py"), encoding="utf-8").read()
        for keep in ("def bucket_for", '"resolution_state"', '"source_type"'):
            self.assertIn(keep, res, keep)


class TestHomeActionBadgeNeutralization(unittest.TestCase):
    """Phase 1b blocker fix: the homepage must stop server-rendering the
    global, unscoped approvals_count. Prove the count queries are gone and
    the badge is a widget-owned hidden placeholder."""
    @classmethod
    def setUpClass(cls):
        cls._saved = sys.modules.get("frappe")
        _install_tripwire_frappe()
        for m in ("ecentric_workspace.legacy_pages.home.page_sync",
                  "ecentric_workspace.approval_center.page_sync_util"):
            sys.modules.pop(m, None)
        cls.hp = importlib.import_module("ecentric_workspace.legacy_pages.home.page_sync")

    @classmethod
    def tearDownClass(cls):
        if cls._saved is not None:
            sys.modules["frappe"] = cls._saved

    def _fixture(self):
        hp = self.hp
        return ('<div class="content">' + hp._LEAVE_SET_LEGACY + hp._SO_SET_LEGACY +
                hp._APPROVALS_SET_LEGACY +
                '<div class="stat-card">' + hp._KPI_VAL_LEGACY +
                '<div class="stat-label">Phê duyệt chờ</div>' + hp._KPI_META_LEGACY + '</div>'
                '<div class="panel-title">Việc cần làm ' + hp._BADGE_LEGACY + '</div>'
                '<div class="approval-list">{% if approvals_count == 0 %}e{% else %}x{% endif %}</div>'
                '<script id="ec-chatbot-js">g()</script></div>')

    def test_global_count_removed_no_false_zero_widget_owned(self):
        new, changed = self.hp.neutralize_legacy_action_counts(self._fixture())
        self.assertEqual(changed, 6)
        # #1/#6 legacy global count logic GONE
        self.assertNotIn("frappe.db.count('Leave Application'", new)
        self.assertNotIn("frappe.db.count('Sales Order'", new)
        # badge = neutral hidden widget-owned placeholder
        self.assertEqual(new.count('data-ec-ac-badge="1"'), 1)
        self.assertIn('data-ec-ac-badge="1" hidden', new)
        self.assertNotIn(self.hp._BADGE_LEGACY, new)
        # KPI "Phê duyệt chờ": widget-owned + NEUTRAL "—", NOT a false 0
        self.assertEqual(new.count('data-ec-ac-kpi="approval"'), 1)
        self.assertIn('data-ec-ac-kpi="approval">—</div>', new)
        self.assertNotIn('<div class="stat-value">0</div>', new)
        self.assertNotIn(self.hp._KPI_VAL_LEGACY, new)
        # meta: session-scoped placeholder (widget fills "X yêu cầu cần phản hồi")
        self.assertEqual(new.count('data-ec-ac-kpi-meta="1"'), 1)
        self.assertNotIn(self.hp._KPI_META_LEGACY, new)
        self.assertIn('ec-chatbot-js', new)

    def test_idempotent_and_byteproof(self):
        fx = self._fixture()
        new, _ = self.hp.neutralize_legacy_action_counts(fx)
        again, c2 = self.hp.neutralize_legacy_action_counts(new)
        self.assertEqual(again, new)
        self.assertEqual(c2, 0)
        def strip(h):
            for a, b in self.hp._NEUTRALIZE:
                h = h.replace(a, "@@").replace(b, "@@")
            return h
        self.assertEqual(strip(fx), strip(new))     # only the 4 zones change

    def test_refuses_unknown_state(self):
        with self.assertRaises(ValueError):
            self.hp.neutralize_legacy_action_counts("<div>no badge</div>")

    def test_partial_state_refused(self):
        # badge neutralized but a count query left -> refuse (fail loud)
        bad = ('data-ec-ac-badge="1"' + self.hp._LEAVE_SET_LEGACY)
        with self.assertRaises(ValueError):
            self.hp.neutralize_legacy_action_counts(bad)

    def test_sync_endpoint_sm_gated(self):
        src = open(os.path.join(APP, "legacy_pages", "home", "page_sync.py"),
                   encoding="utf-8").read()
        self.assertIn("def sync_home_action_badge", src)
        self.assertIn("System Manager", src)
        self.assertIn("dynamic_template stays 1", src)


if __name__ == "__main__":
    unittest.main()
