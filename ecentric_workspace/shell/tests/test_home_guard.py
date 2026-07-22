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
        for keep in ("def get_action_items", "def get_my_requests_summary",
                     "_engine_level_due", "counts[it[\"bucket\"]]"):
            self.assertIn(keep, api, keep)
        res = open(os.path.join(APP, "action_center", "resolvers.py"), encoding="utf-8").read()
        for keep in ("def bucket_for", '"resolution_state"', '"source_type"'):
            self.assertIn(keep, res, keep)


if __name__ == "__main__":
    unittest.main()
