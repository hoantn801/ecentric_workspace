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
        ax.frappe.get_all = lambda *a, **k: [{"name": "LEAK", "status": "Active"}]
        res = ax.list_exemptions()
        self.assertEqual(res["rows"], [])                     # never the LEAK row
        self.assertEqual(res["counts"]["all"], 0)

    def test_list_supervisor_is_unscoped_by_brand(self):
        perms = sys.modules["ecentric_workspace.alerts.permissions"]
        perms._allowed = perms.ALL_BRANDS
        from ecentric_workspace.alerts import api_exemptions as ax
        ax.frappe.get_all = lambda *a, **k: [
            {"name": "EC-EXEMPT-1", "status": "Active", "effective_from": None,
             "effective_to": None, "modified": "2026-06-01"}]
        rows = ax.list_exemptions(filters={"lifecycle_state": "all"})["rows"]
        self.assertEqual([r["name"] for r in rows], ["EC-EXEMPT-1"])


def _exrow(name, status="Active", platform="Shopee", seller_sku="SKU1",
           reason="Gift / Freebie", ef=None, et=None, brand="B", modified="2026-06-01"):
    return dict(name=name, status=status, platform=platform, seller_sku=seller_sku,
                reason=reason, effective_from=ef, effective_to=et, brand=brand,
                notes="", exempted_by="u", modified=modified)


def _ex_liststub(all_rows):
    """get_all stub honouring api_exemptions' filter dict (brand =/in, platform/reason
    =, seller_sku like). Returns dict copies so lifecycle assignment doesn't leak."""
    def ga(*a, **k):
        q = k.get("filters") or {}
        out = []
        for r in all_rows:
            ok = True
            for key, cond in q.items():
                rv = r.get(key)
                if isinstance(cond, list) and cond and cond[0] == "in":
                    if rv not in cond[1]:
                        ok = False
                elif isinstance(cond, list) and cond and cond[0] == "like":
                    if cond[1].strip("%").lower() not in str(rv or "").lower():
                        ok = False
                elif rv != cond:
                    ok = False
            if ok:
                out.append(dict(r))
        return out
    return ga


# today() is stubbed to 2026-06-16 (frappe.utils.nowdate).
_TODAY = "2026-06-16"
_DATASET = [
    _exrow("A", ef="2026-06-01", et="2026-06-30"),                 # effective
    _exrow("B", ef="2026-07-01", et="2026-07-31"),                 # upcoming
    _exrow("C", ef="2026-05-01", et="2026-05-31"),                 # expired
    _exrow("D", status="Inactive"),                                # inactive
    _exrow("E", ef=None, et=None),                                 # effective (open both)
    _exrow("F", ef=None, et="2026-12-31"),                         # effective (open start)
    _exrow("G", ef="2026-01-01", et=None),                         # effective (open end)
]


class TestDeriveLifecycle(unittest.TestCase):
    def test_each_state_and_open_ended(self):
        from ecentric_workspace.alerts import api_exemptions as ax
        d = lambda r: ax.derive_lifecycle(r, _TODAY)
        self.assertEqual(d(_DATASET[0]), "effective")
        self.assertEqual(d(_DATASET[1]), "upcoming")
        self.assertEqual(d(_DATASET[2]), "expired")
        self.assertEqual(d(_DATASET[3]), "inactive")
        self.assertEqual(d(_DATASET[4]), "effective")   # open both
        self.assertEqual(d(_DATASET[5]), "effective")   # open start
        self.assertEqual(d(_DATASET[6]), "effective")   # open end


class TestListLifecycle(unittest.TestCase):
    def setUp(self):
        self.perms = sys.modules["ecentric_workspace.alerts.permissions"]
        self.perms._allowed = self.perms.ALL_BRANDS
        from ecentric_workspace.alerts import api_exemptions as ax
        self.ax = ax
        ax.frappe.get_all = _ex_liststub(_DATASET)

    def test_counts_are_status_based(self):
        # 6 Active (A,B,C,E,F,G) + 1 Inactive (D); dates no longer split the tabs.
        res = self.ax.list_exemptions(filters={"lifecycle_state": "active"})
        self.assertEqual(res["counts"], {"active": 6, "inactive": 1, "all": 7})

    def test_default_tab_active(self):
        res = self.ax.list_exemptions(filters={})
        self.assertEqual(res["lifecycle_state"], "active")
        self.assertEqual(res["total"], 6)
        self.assertEqual({r["name"] for r in res["rows"]}, {"A", "B", "C", "E", "F", "G"})

    def test_each_tab_total(self):
        for state, n in (("active", 6), ("inactive", 1), ("all", 7)):
            res = self.ax.list_exemptions(filters={"lifecycle_state": state})
            self.assertEqual(res["total"], n, state)

    def test_inactive_tab_only_inactive(self):
        res = self.ax.list_exemptions(filters={"lifecycle_state": "inactive"})
        self.assertEqual([r["name"] for r in res["rows"]], ["D"])

    def test_unknown_state_falls_back_to_active(self):
        res = self.ax.list_exemptions(filters={"lifecycle_state": "bogus"})
        self.assertEqual(res["lifecycle_state"], "active")
        self.assertEqual(res["total"], 6)

    def test_pagination_and_total(self):
        p1 = self.ax.list_exemptions(filters={"lifecycle_state": "active"}, start=0, page_length=4)
        p2 = self.ax.list_exemptions(filters={"lifecycle_state": "active"}, start=4, page_length=4)
        self.assertEqual(len(p1["rows"]), 4)
        self.assertEqual(len(p2["rows"]), 2)
        self.assertEqual(p1["total"], 6)
        names = {r["name"] for r in p1["rows"]} | {r["name"] for r in p2["rows"]}
        self.assertEqual(names, {"A", "B", "C", "E", "F", "G"})   # no overlap, full coverage

    def test_combined_filters(self):
        rows = list(_DATASET) + [_exrow("Z", platform="Lazada",
                                        seller_sku="GIFT9", ef=None, et=None)]
        self.ax.frappe.get_all = _ex_liststub(rows)
        res = self.ax.list_exemptions(filters={"lifecycle_state": "active",
                                               "platform": "Lazada",
                                               "seller_sku": "gift"})
        self.assertEqual([r["name"] for r in res["rows"]], ["Z"])

    def test_empty_scope_zero_rows_and_counts(self):
        self.perms._allowed = []                    # non-admin, no brands
        res = self.ax.list_exemptions(filters={})
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["counts"], {"active": 0, "inactive": 0, "all": 0})

    def test_brand_scope_limits_counts(self):
        rows = [_exrow("A", brand="B1"), _exrow("B", brand="B2")]
        self.perms._allowed = ["B1"]                # only B1 accessible
        self.ax.frappe.get_all = _ex_liststub(rows)
        res = self.ax.list_exemptions(filters={"lifecycle_state": "all"})
        self.assertEqual(res["counts"]["all"], 1)   # B2 not counted
        self.assertEqual([r["name"] for r in res["rows"]], ["A"])


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


class _FakeDoc:
    def __init__(self):
        self.name = None
        self._f = {}

    def set(self, k, v):
        self._f[k] = v

    def save(self, **k):
        if self._f.get("seller_sku") == "BAD":        # simulate overlap rejection
            raise Exception("Overlapping exemption")
        self.name = "EC-EXEMPT-" + str(self._f.get("seller_sku"))


class TestBulkSave(unittest.TestCase):
    """RC7-C bulk: one request, per-item results, independent savepoints (one failure
    does not abort the others)."""

    def _ax(self):
        from ecentric_workspace.alerts import api_exemptions as ax
        ax.frappe.new_doc = lambda dt: _FakeDoc()
        ax.frappe.db.savepoint = lambda sp: None
        ax.frappe.db.rollback = lambda **k: None
        sys.modules["ecentric_workspace.alerts.permissions"].require_brand_access = lambda *a, **k: None
        return ax

    def test_partial_success_keeps_per_item_results(self):
        ax = self._ax()
        res = ax.bulk_save_exemptions(
            exemptions=[{"seller_sku": "S1"}, {"seller_sku": "BAD"}, {"seller_sku": "S3"}],
            defaults={"brand": "B", "platform": "All", "reason": "Gift / Freebie", "status": "Active"})
        self.assertEqual(res["created"], 2)
        self.assertEqual(res["failed"], 1)
        rmap = {r["seller_sku"]: r for r in res["results"]}
        self.assertTrue(rmap["S1"]["ok"])
        self.assertTrue(rmap["S3"]["ok"])
        self.assertFalse(rmap["BAD"]["ok"])
        self.assertIn("Overlapping", rmap["BAD"]["error"])

    def test_missing_brand_row_fails_only_itself(self):
        ax = self._ax()
        res = ax.bulk_save_exemptions(
            exemptions=[{"seller_sku": "S1", "brand": "B"}, {"seller_sku": "S2", "brand": ""}],
            defaults={"platform": "All", "reason": "Gift / Freebie", "status": "Active"})
        self.assertEqual(res["created"], 1)
        self.assertEqual(res["failed"], 1)

    def test_out_of_scope_brand_row_fails(self):
        ax = self._ax()
        def _gate(user, brand):
            if brand == "OTHER":
                raise Exception("Out of scope")
        sys.modules["ecentric_workspace.alerts.permissions"].require_brand_access = _gate
        res = ax.bulk_save_exemptions(
            exemptions=[{"seller_sku": "S1", "brand": "B"}, {"seller_sku": "S2", "brand": "OTHER"}],
            defaults={"platform": "All", "reason": "Gift / Freebie", "status": "Active"})
        self.assertEqual(res["created"], 1)
        self.assertIn("scope", " ".join(r.get("error", "") for r in res["results"]).lower())


class _D(dict):
    """dict with attribute access (mimics frappe._dict: r.status AND r['name'])."""
    __getattr__ = dict.get


class _UpsertDoc:
    def __init__(self, name=None):
        self.name = name
        self.brand = self.platform = self.seller_sku = self.reason = self.status = None

    def save(self, **k):
        if not self.name:
            self.name = "EC-EXEMPT-" + str(self.seller_sku)


class TestGiftUpsert(unittest.TestCase):
    """RC7 CSV IS_GIFT routing helper: idempotent create / reactivate / already-exists,
    never a duplicate. Canonical key = brand + platform + seller_sku (Shop ignored)."""

    def _ax(self):
        from ecentric_workspace.alerts import api_exemptions as ax
        return ax

    def test_already_active_is_idempotent(self):
        ax = self._ax()
        ax.frappe.get_all = lambda *a, **k: [_D(name="E1", status="Active")]
        ax.frappe.get_doc = lambda *a, **k: self.fail("must not write")
        ax.frappe.new_doc = lambda *a, **k: self.fail("must not create")
        self.assertEqual(ax.upsert_gift_exemption("B", "Shopee", "S1"), ("already_exists", "E1"))

    def test_inactive_is_reactivated(self):
        ax = self._ax()
        ax.frappe.get_all = lambda *a, **k: [_D(name="E2", status="Inactive")]
        doc = _UpsertDoc("E2")
        ax.frappe.get_doc = lambda *a, **k: doc
        outcome, name = ax.upsert_gift_exemption("B", "Shopee", "S1")
        self.assertEqual(outcome, "exemption_reactivated")
        self.assertEqual(name, "E2")
        self.assertEqual(doc.status, "Active")
        self.assertEqual(doc.reason, "Gift / Freebie")

    def test_none_creates_active(self):
        ax = self._ax()
        ax.frappe.get_all = lambda *a, **k: []
        ax.frappe.new_doc = lambda dt: _UpsertDoc()
        outcome, name = ax.upsert_gift_exemption("B", "Shopee", "S9")
        self.assertEqual(outcome, "exemption_created")
        self.assertTrue(name.endswith("S9"))


class TestControllerNameErrorGuard(unittest.TestCase):
    """RC7 production fix: the EC Price Policy controller must IMPORT the policy_scope
    MODULE where it calls policy_scope.canonical_guard_conflict (else set_policy_status
    -> validate() raised NameError: name 'policy_scope' is not defined)."""

    def test_controller_imports_policy_scope_module(self):
        from ecentric_workspace.alerts.services import exemption_guard as _eg
        alerts = os.path.dirname(os.path.dirname(_eg.__file__))
        src = open(os.path.join(alerts, "doctype", "ec_price_policy",
                                "ec_price_policy.py"), encoding="utf-8").read()
        self.assertIn("from ecentric_workspace.alerts.services import policy_scope", src)
        self.assertIn("policy_scope.canonical_guard_conflict", src)


if __name__ == "__main__":
    unittest.main()
