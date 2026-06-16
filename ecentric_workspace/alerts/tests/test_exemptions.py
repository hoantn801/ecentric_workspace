"""RC7-C Gift/Freebie Price Guard exemption tests. The resolver match/window logic is
pure (stubbed frappe.get_all); the engine-skip / coverage-exclude / baseline-exclude
wiring is asserted at the source level (proving ONE shared resolver is reused at the
three insertion points, not duplicated).

    bench run-tests --module ecentric_workspace.alerts.tests.test_exemptions
"""
import os
import sys
import types
import unittest

if "frappe" not in sys.modules:
    _fr = types.ModuleType("frappe")
    _fr.get_all = lambda *a, **k: []
    _fr.whitelist = lambda *a, **k: (lambda f: f)
    _fr._ = lambda s: s
    _fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    _fr.session = types.SimpleNamespace(user="tester")
    _fr.db = types.SimpleNamespace(sql=lambda *a, **k: [])
    sys.modules["frappe"] = _fr
    _u = types.ModuleType("frappe.utils")
    _u.nowdate = lambda: "2026-06-16"
    _u.add_days = lambda d, n: "2026-05-17"
    _u.now_datetime = lambda: "2026-06-16 00:00:00"
    sys.modules["frappe.utils"] = _u
# stub the permissions module so api_exemptions imports without a site (the brand-scope
# model itself is covered by the existing permission test suites; here we only re-check
# the empty-scope guard specific to the new endpoints).
if "ecentric_workspace.alerts.permissions" not in sys.modules:
    _perms = types.ModuleType("ecentric_workspace.alerts.permissions")
    _perms.ALL_BRANDS = "*"
    _perms._allowed = {}
    _perms.require_alert_center_access = lambda *a, **k: _perms._allowed
    _perms.require_brand_access = lambda *a, **k: None
    sys.modules["ecentric_workspace.alerts.permissions"] = _perms

from ecentric_workspace.alerts.services import exemption_guard as eg  # noqa: E402

SVC = os.path.dirname(eg.__file__)


def _rows(*recs):
    return [types.SimpleNamespace(**r) for r in recs]


def _ex(name="EC-EXEMPT-1", brand="B", platform="Shopee", seller_sku="SKU1",
        status="Active", reason="Gift / Freebie", ef=None, et=None):
    return dict(name=name, brand=brand, platform=platform, seller_sku=seller_sku,
                status=status, reason=reason, effective_from=ef, effective_to=et)


def _filtered_stub(all_rows):
    """get_all stub that honours the brand/seller_sku/status/platform-in filters the
    resolver passes, so platform/SKU/status mismatches are exercised realistically."""
    def ga(*a, **k):
        flt = k.get("filters") or {}
        out = []
        for r in all_rows:
            ok = True
            for key, val in flt.items():
                rv = getattr(r, key, None)
                if isinstance(val, list) and val and val[0] == "in":
                    if rv not in val[1]:
                        ok = False
                elif rv != val:
                    ok = False
            if ok:
                out.append(r)
        return out
    return ga


class TestWindows(unittest.TestCase):
    def test_overlap_cases(self):
        self.assertTrue(eg.windows_overlap("2026-06-01", "2026-06-30", "2026-06-15", "2026-07-15"))
        self.assertFalse(eg.windows_overlap("2026-06-01", "2026-06-10", "2026-06-11", "2026-06-20"))
        self.assertTrue(eg.windows_overlap(None, None, "2026-06-01", "2026-06-02"))


class TestMatch(unittest.TestCase):
    def _set(self, rows):
        eg.frappe.get_all = _filtered_stub(rows)

    def test_active_in_window_matches(self):
        self._set(_rows(_ex(ef="2026-06-01", et="2026-06-30")))
        self.assertTrue(eg.is_exempt("B", "Shopee", "SKU1", on_date="2026-06-15"))

    def test_outside_window_no_match(self):
        self._set(_rows(_ex(ef="2026-06-01", et="2026-06-10")))
        self.assertFalse(eg.is_exempt("B", "Shopee", "SKU1", on_date="2026-06-20"))

    def test_open_window_matches(self):
        self._set(_rows(_ex(ef=None, et=None)))
        self.assertTrue(eg.is_exempt("B", "Shopee", "SKU1", on_date="2030-01-01"))

    def test_inactive_does_not_match(self):
        self._set(_rows(_ex(status="Inactive", ef=None, et=None)))
        self.assertFalse(eg.is_exempt("B", "Shopee", "SKU1", on_date="2026-06-15"))

    def test_different_platform_no_match(self):
        # exemption is Shopee-specific; a Lazada line must not match it.
        self._set(_rows(_ex(platform="Shopee", ef=None, et=None)))
        self.assertFalse(eg.is_exempt("B", "Lazada", "SKU1", on_date="2026-06-15"))

    def test_platform_all_matches_any(self):
        self._set(_rows(_ex(platform="All", ef=None, et=None)))
        self.assertTrue(eg.is_exempt("B", "Lazada", "SKU1", on_date="2026-06-15"))

    def test_different_sku_no_match(self):
        self._set(_rows(_ex(seller_sku="SKU1", ef=None, et=None)))
        self.assertFalse(eg.is_exempt("B", "Shopee", "SKU2", on_date="2026-06-15"))

    def test_match_returns_name_and_reason(self):
        self._set(_rows(_ex(name="EC-EXEMPT-9", reason="Gift / Freebie", ef=None, et=None)))
        m = eg.match_exemption("B", "Shopee", "SKU1", on_date="2026-06-15")
        self.assertEqual(m.name, "EC-EXEMPT-9")
        self.assertEqual(m.reason, "Gift / Freebie")

    def test_missing_args_no_match(self):
        self._set(_rows(_ex(ef=None, et=None)))
        self.assertFalse(eg.is_exempt("", "Shopee", "SKU1"))
        self.assertFalse(eg.is_exempt("B", "Shopee", ""))


class TestSqlMatcher(unittest.TestCase):
    def test_predicate_shape(self):
        sql = eg.exempt_exists_sql("ol.brand", "ol.platform", "oi.seller_sku", "%(today)s")
        for frag in ("`tabEC Price Guard Exemption`", "ge.status = 'Active'",
                     "ge.brand = ol.brand", "ge.platform = ol.platform OR ge.platform = 'All'",
                     "ge.seller_sku = oi.seller_sku",
                     "ge.effective_from IS NULL OR ge.effective_from <= %(today)s",
                     "ge.effective_to IS NULL OR ge.effective_to >= %(today)s"):
            self.assertIn(frag, sql)


class TestInsertionWiring(unittest.TestCase):
    """The three source-of-truth modules each reuse the ONE shared resolver."""

    def _src(self, fn):
        return open(os.path.join(SVC, fn), encoding="utf-8").read()

    def test_engine_skips_before_policy_lookup(self):
        s = self._src("alert_engine.py")
        self.assertIn("exemption_guard.match_exemption", s)
        self.assertIn("exemption_guard.SKIP_RESULT", s)
        # the exemption check must run BEFORE the policy lookup, and be a guarded skip.
        self.assertLess(s.index("exemption_guard.match_exemption"),
                        s.index("policy_lookup.find_policy("))
        self.assertIn("if _ex:", s)

    def test_coverage_excludes_exempt(self):
        self.assertIn("exemption_guard.exempt_exists_sql", self._src("policy_coverage.py"))

    def test_baseline_excludes_exempt(self):
        self.assertIn("exemption_guard.exempt_exists_sql", self._src("baseline.py"))

    def test_single_shared_resolver(self):
        # the SQL matcher + the python matcher are defined ONCE, in exemption_guard.
        eg_src = self._src("exemption_guard.py")
        self.assertIn("def exempt_exists_sql", eg_src)
        self.assertIn("def match_exemption", eg_src)
        # the matcher is NOT redefined in the consumers.
        for fn in ("alert_engine.py", "policy_coverage.py", "baseline.py"):
            self.assertNotIn("def exempt_exists_sql", self._src(fn))


class TestApiBrandScope(unittest.TestCase):
    """RC7-C security: the new endpoints reuse the existing Alert Center brand-scope
    model, and an EMPTY brand scope must NOT become an unrestricted query."""

    def test_list_empty_scope_returns_empty_without_leaking(self):
        perms = sys.modules["ecentric_workspace.alerts.permissions"]
        perms._allowed = {}                                   # non-admin, no brands
        from ecentric_workspace.alerts import api_exemptions as ax
        ax.frappe.get_all = lambda *a, **k: [types.SimpleNamespace(name="LEAK")]
        self.assertEqual(ax.list_exemptions(), {"rows": []})  # never the LEAK row

    def test_list_supervisor_is_unscoped_by_brand(self):
        perms = sys.modules["ecentric_workspace.alerts.permissions"]
        perms._allowed = perms.ALL_BRANDS
        from ecentric_workspace.alerts import api_exemptions as ax
        ax.frappe.get_all = lambda *a, **k: [types.SimpleNamespace(name="EC-EXEMPT-1")]
        rows = ax.list_exemptions().get("rows")
        self.assertEqual([r.name for r in rows], ["EC-EXEMPT-1"])


class TestBaselineQueryCount(unittest.TestCase):
    """RC7-C performance: the exemption integration must NOT add a DB query per
    historical order line — it is folded into the SINGLE existing history query."""

    def test_history_issues_exactly_one_sql_call(self):
        from ecentric_workspace.alerts.services import baseline
        calls = {"n": 0}

        def _sql(*a, **k):
            calls["n"] += 1
            return []
        baseline.frappe.db.sql = _sql
        baseline.get_baseline("B", "Shopee", None, None, "SKU1")
        self.assertEqual(calls["n"], 1,
                         "baseline must issue exactly ONE history query (no per-line / "
                         "per-exemption N+1); the exemption is a correlated SQL predicate")

    def test_exemption_predicate_is_in_the_history_query(self):
        from ecentric_workspace.alerts.services import baseline
        captured = {}

        def _sql(q, params, *a, **k):
            captured["q"] = q
            return []
        baseline.frappe.db.sql = _sql
        baseline.get_baseline("B", "Shopee", None, None, "SKU1")
        self.assertIn("tabEC Price Guard Exemption", captured.get("q", ""),
                      "the exemption exclusion must be part of the single history query")


if __name__ == "__main__":
    unittest.main()
