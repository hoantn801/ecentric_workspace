"""Retire missing_policy from operational Alerts (batch 2026-06-14).

Two layers, both runnable WITHOUT a bench/DB:

  1. TestPolicyCoverage - drives the REAL services.policy_coverage with a stubbed
     frappe (frappe.db.sql canned), proving the canonical coverage definition:
     window resolution, brand-scope handling, grouped counts, and the coverage
     report (chip count == full distinct count == modal list length when capped),
     plus the _COVERED predicate mirrors policy_lookup.find_policy's 6 levels.

  2. Source-assertion classes - static guards that the engine no longer CREATES
     missing_policy alerts, that the list/KPI/dashboard default-exclude it, that
     the Setup ToDo reads the canonical coverage, and that the retirement patch
     closes (never hard-deletes) and is registered.

    bench run-tests --module ecentric_workspace.alerts.tests.test_missing_policy_retired
"""
import os
import sys
import types
import unittest


class _AttrDict(dict):
    __getattr__ = dict.get


_MISSING = object()  # sentinel: attribute was absent on the stub before patching


def _stub_frappe():
    """Install a minimal frappe so policy_coverage imports cleanly off-bench.
    If a real frappe is already present (bench), leave it - the canned db.sql is
    only attached for these tests via the harness setUp instead."""
    if "frappe" in sys.modules and not getattr(sys.modules["frappe"], "_ec_stub", False):
        return sys.modules["frappe"], False
    f = types.ModuleType("frappe")
    f._ec_stub = True
    f.conf = {}
    f.db = types.SimpleNamespace(sql=lambda *a, **k: [])
    utils = types.ModuleType("frappe.utils")
    utils.add_days = lambda d, n: "2026-05-15"
    utils.nowdate = lambda: "2026-06-14"
    f.utils = utils
    sys.modules["frappe"] = f
    sys.modules["frappe.utils"] = utils
    return f, True


_FK, _IS_STUB = _stub_frappe()
from ecentric_workspace.alerts.services import policy_coverage as pc  # noqa: E402


def _rows(*specs):
    return [_AttrDict(brand=b, seller_sku=s, product_name=p, rsp_price=0,
                      order_lines=o, last_order="x") for (b, s, p, o) in specs]


@unittest.skipUnless(_IS_STUB, "coverage unit layer runs on the stubbed-frappe harness")
class TestPolicyCoverage(unittest.TestCase):
    def setUp(self):
        self._rows = []
        self._total = 0
        _FK.conf = {}

        def sql(q, params=None, as_dict=False):
            if "GROUP BY" in q:
                return list(self._rows)
            return [_AttrDict(n=self._total)]
        _FK.db.sql = sql

    # ---- window resolution ----
    def test_window_default_30(self):
        self.assertEqual(pc.window_days(), 30)

    def test_window_arg_and_conf_override(self):
        self.assertEqual(pc.window_days(7), 7)
        _FK.conf = {"ec_alerts_coverage_window_days": "45"}
        self.assertEqual(pc.window_days(), 45)

    def test_window_bad_conf_falls_back(self):
        _FK.conf = {"ec_alerts_coverage_window_days": "oops"}
        self.assertEqual(pc.window_days(), 30)

    # ---- brand scope ----
    def test_empty_scope_short_circuits_without_query(self):
        self._rows = _rows(("B", "S", "P", 1))
        self.assertEqual(pc.missing_rows([]), [])          # [] = empty scope -> []
        self.assertEqual(pc.missing_rows(["", None]), [])  # all-blank -> []

    def test_none_brands_queries_all(self):
        self._rows = _rows(("B1", "S1", "P", 3), ("B2", "S2", "P", 1))
        self.assertEqual(len(pc.missing_rows(None)), 2)

    # ---- grouped counts (chip) ----
    def test_counts_grouped_by_brand(self):
        self._rows = _rows(("B1", "S1", "P", 3), ("B1", "S2", "P", 2), ("B2", "S3", "P", 1))
        self.assertEqual(pc.missing_counts(None), {"B1": 2, "B2": 1})

    def test_missing_count_single_brand_and_blank(self):
        self._rows = _rows(("B1", "S1", "P", 3), ("B1", "S2", "P", 2))
        self.assertEqual(pc.missing_count("B1"), 2)
        self.assertEqual(pc.missing_count(""), 0)

    # ---- coverage report: chip count == modal list (one definition) ----
    def test_report_shape_and_pct(self):
        self._rows = _rows(("B1", "S1", "P", 3), ("B1", "S2", "P", 2))
        self._total = 10
        r = pc.coverage_report("B1")
        self.assertEqual(r["missing_count"], 2)
        self.assertEqual(len(r["missing"]), 2)
        self.assertEqual(r["checked"], 10)
        self.assertEqual(r["coverage_pct"], 80.0)
        self.assertEqual(r["days"], 30)

    def test_report_count_is_full_even_when_list_capped(self):
        self._rows = _rows(*[("B1", "S%d" % i, "P", 1) for i in range(250)])
        self._total = 300
        r = pc.coverage_report("B1", limit=200)
        self.assertEqual(r["missing_count"], 250)   # chip = FULL distinct count
        self.assertEqual(len(r["missing"]), 200)    # modal display capped

    def test_report_pct_none_without_orders(self):
        self._rows = []
        self._total = 0
        self.assertIsNone(pc.coverage_report("B1")["coverage_pct"])

    # ---- predicate mirrors find_policy existence (covered == find_policy hit) ----
    def test_covered_predicate_mirrors_find_policy_levels(self):
        c = pc._COVERED
        for marker in ("pp.status = 'Active'", "pp.is_brand_fallback = 1",
                       "pp.platform = 'All'", "pp.effective_from IS NULL",
                       "pp.effective_to", "pp.seller_sku = oi.seller_sku",
                       "pp.item = oi.item", "pp.shop = ol.shop"):
            self.assertIn(marker, c, marker)


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestEngineNoLongerCreatesMissingPolicy(unittest.TestCase):
    def test_engine_does_not_create_missing_policy_alert(self):
        s = _src("services/alert_engine.py")
        # the no-policy branch must NOT raise an alert anymore...
        self.assertNotIn('rule_code="missing_policy"', s)
        self.assertNotIn("missing_policy_key(", s)
        # ...but still mark the line for debug and skip it.
        self.assertIn('line.check_result = "Missing Rule"', s)
        self.assertIn("missing_policy_skipped", s)

    def test_other_rules_still_created(self):
        s = _src("services/alert_engine.py")
        # missing_brand_mapping + the price violation path are untouched.
        self.assertIn('rule_code="missing_brand_mapping"', s)
        self.assertIn("_record_price_violation(", s)


class TestListAndKpiExcludeMissingPolicy(unittest.TestCase):
    # Pre-E2E 2026-06-14: the per-API hardcoded ["missing_policy"] exclusion was
    # replaced by ONE canonical classifier (services.rule_classification). These
    # guards now assert the shared helper is used (missing_policy is still
    # default-excluded as a SETUP rule, plus missing_brand_mapping is too).
    def test_alerts_list_uses_canonical_classifier(self):
        s = _src("api_alerts.py")
        self.assertIn("rule_classification as rclass", s)
        self.assertIn("rclass.rule_code_condition(f)", s)
        self.assertIn("rclass.non_operational_rule_codes()", s)

    def test_dashboard_uses_canonical_classifier_and_supports_not_in(self):
        s = _src("api_dashboard.py")
        self.assertIn("rule_classification as rclass", s)
        self.assertIn("rclass.rule_code_condition(f)", s)
        self.assertIn('elif op == "not in":', s)         # _where can render it

    def test_kpi_cards_separate_setup_from_operational(self):
        for mod in ("api_alerts.py", "api_dashboard.py"):
            s = _src(mod)
            # Setup Issues counted via the canonical setup set...
            self.assertIn("rclass.setup_rule_codes()", s)
            # ...and the old single-rule hardcoded card hack is gone.
            self.assertNotIn('rule_code=("in", ["missing_brand_mapping"])', s)
            self.assertNotIn('["rule_code", "in",\n                                       ["missing_brand_mapping"]]', s)

    def test_canonical_classifier_keeps_missing_policy_and_mapping_as_setup(self):
        from ecentric_workspace.alerts.services import rule_classification as rc
        self.assertIn("missing_policy", rc.SETUP_RULES)
        self.assertIn("missing_brand_mapping", rc.SETUP_RULES)
        self.assertNotIn("missing_policy", rc.OPERATIONAL_RULES)
        self.assertNotIn("missing_brand_mapping", rc.OPERATIONAL_RULES)


class TestSetupTodoUsesCanonicalCoverage(unittest.TestCase):
    def test_remaining_reads_policy_coverage_not_ec_alert(self):
        s = _src("services/case_todo.py")
        self.assertIn("from ecentric_workspace.alerts.services import policy_coverage", s)
        self.assertIn("policy_coverage.missing_count(brand)", s)
        # no longer counts ACTIVE missing_policy EC Alert rows
        self.assertNotIn("rule_code = 'missing_policy'", s)


class TestRetirementPatch(unittest.TestCase):
    def test_patch_registered(self):
        txt = _src("../patches.txt")
        self.assertIn(
            "ecentric_workspace.alerts.patches.p004_retire_missing_policy_alerts", txt)

    def test_patch_closes_and_never_hard_deletes(self):
        s = _src("patches/p004_retire_missing_policy_alerts.py")
        self.assertIn('_CLOSE_STATUS = "Closed"', s)
        self.assertIn("Retired: coverage gap is now tracked through Price Setup.", s)
        self.assertIn("autosync_suspended", s)            # one recompute per brand
        self.assertIn("sync_brand_setup", s)
        # Audit is the controller's (track_changes Version + _stamp_resolution);
        # NO manual Comment -> no duplicate timeline event.
        self.assertNotIn("add_comment", s)
        # NO hard delete of any kind.
        self.assertNotIn("frappe.db.delete", s)
        self.assertNotIn(".delete(", s)
        self.assertNotIn("DELETE FROM", s.upper())

    def test_patch_only_touches_active_missing_policy(self):
        s = _src("patches/p004_retire_missing_policy_alerts.py")
        self.assertIn('"rule_code": _RULE', s)
        self.assertIn("cl.ACTIVE_STATUSES", s)
        self.assertIn("is_terminal", s)                   # terminal records skipped


@unittest.skipUnless(_IS_STUB, "equivalence layer runs on the stubbed-frappe harness")
class TestCoverageMatchesFindPolicy(unittest.TestCase):
    """INVARIANT (the whole point of policy_coverage): the _COVERED NOT-EXISTS
    predicate agrees with policy_lookup.find_policy on identical fixtures -
    covered  <=>  find_policy returns a policy - across all 6 levels, effective
    window inclusivity, and Draft/Inactive/future/expired/scope exclusions. The
    REAL predicate string is executed in SQLite; find_policy runs against the
    same rows via a stubbed frappe. No bench / DB. If either side drifts, this
    fails."""

    TODAY, YDAY, TMRW = "2026-06-14", "2026-06-13", "2026-06-15"
    COLS = ["name", "brand", "status", "platform", "shop", "item",
            "seller_sku", "is_brand_fallback", "effective_from", "effective_to"]
    LINE = {"brand": "B", "platform": "Shopee", "shop": "S1", "item": "ITM", "seller_sku": "SKU"}

    def setUp(self):
        import importlib
        self._pol = []
        self._mod = importlib.import_module(
            "ecentric_workspace.alerts.services.policy_lookup")

        def match(row, filters):
            for k, v in filters.items():
                if isinstance(v, tuple):
                    op = v[0]
                    if op == "is" and v[1] == "not set":
                        if row.get(k) not in (None, ""):
                            return False
                    elif op == "in":
                        if row.get(k) not in v[1]:
                            return False
                    else:
                        return False
                elif row.get(k) != v:
                    return False
            return True

        new_get_all = lambda dt, filters=None, fields=None, **k: [
            _AttrDict(name=p["name"], effective_from=p.get("effective_from"),
                      effective_to=p.get("effective_to"))
            for p in self._pol if match(p, filters or {})]
        new_get_doc = lambda dt, name: next(
            (_AttrDict(**p) for p in self._pol if p["name"] == name), None)
        new_nowdate = lambda: self.TODAY

        # Save + patch SAFELY: the stubbed frappe may not define get_all/get_doc
        # at all (standalone `python -m unittest`), so capture a sentinel when the
        # attribute is absent and delete it again in tearDown - never read it
        # directly (that was the AttributeError).
        self._patches = []
        for obj, name, value in ((_FK, "get_all", new_get_all),
                                 (_FK, "get_doc", new_get_doc),
                                 (_FK.utils, "nowdate", new_nowdate)):
            self._patches.append((obj, name, getattr(obj, name, _MISSING)))
            setattr(obj, name, value)

    def tearDown(self):
        for obj, name, original in reversed(self._patches):
            if original is _MISSING:
                if hasattr(obj, name):
                    delattr(obj, name)
            else:
                setattr(obj, name, original)

    def _P(self, **kw):
        base = {"name": "PP", "brand": "B", "status": "Active", "platform": None,
                "shop": None, "item": None, "seller_sku": None,
                "is_brand_fallback": 0, "effective_from": None, "effective_to": None}
        base.update(kw)
        return base

    def _covered_sql(self, policies, line, shops=None):
        """Execute the REAL pc._COVERED predicate in SQLite. Mirrors production's
        FROM/JOIN shape EXACTLY by reusing pc._SHOP_JOIN, so brand is resolved as
        COALESCE(NULLIF(ol.brand,''), s.brand) (own brand wins; Active shop
        mapping is the fallback). `shops` (default none) seeds the shop-mapping
        table for NULL/blank-brand resolution cases."""
        import sqlite3
        sql = pc._COVERED.replace("%(today)s", ":today")
        db = sqlite3.connect(":memory:")
        c = db.cursor()
        c.execute("CREATE TABLE `tabEC Price Policy` (name TEXT, brand TEXT, status TEXT, "
                  "platform TEXT, shop TEXT, item TEXT, seller_sku TEXT, "
                  "is_brand_fallback INT, effective_from TEXT, effective_to TEXT)")
        # omisell_shop_id added so the production shop-mapping LEFT JOIN resolves.
        c.execute("CREATE TABLE `tabEC Marketplace Order Log` (name TEXT, brand TEXT, "
                  "platform TEXT, shop TEXT, omisell_shop_id TEXT)")
        c.execute("CREATE TABLE `tabEC Marketplace Order Item` (parent TEXT, seller_sku TEXT, item TEXT)")
        # shop->brand mapping table referenced by pc._SHOP_JOIN (alias s).
        c.execute("CREATE TABLE `tabEC Marketplace Shop` (name TEXT, omisell_shop_id TEXT, "
                  "brand TEXT, status TEXT)")
        for p in policies:
            c.execute("INSERT INTO `tabEC Price Policy` VALUES (?,?,?,?,?,?,?,?,?,?)",
                      tuple(p.get(k) for k in self.COLS))
        c.execute("INSERT INTO `tabEC Marketplace Order Log` VALUES (?,?,?,?,?)",
                  ("OL1", line.get("brand"), line["platform"], line.get("shop"),
                   line.get("omisell_shop_id")))
        c.execute("INSERT INTO `tabEC Marketplace Order Item` VALUES (?,?,?)",
                  ("OL1", line.get("seller_sku"), line.get("item")))
        for i, sh in enumerate(shops or []):
            c.execute("INSERT INTO `tabEC Marketplace Shop` VALUES (?,?,?,?)",
                      ("SH%d" % i, sh.get("omisell_shop_id"), sh.get("brand"),
                       sh.get("status", "Active")))
        # Same join shape as production (no %-format: pc._SHOP_JOIN/_COVERED have
        # no '%' left after the :today swap, so concatenate to stay literal-safe).
        query = ("SELECT CASE WHEN " + sql + " THEN 1 ELSE 0 END "
                 "FROM `tabEC Marketplace Order Item` oi "
                 "JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name "
                 + pc._SHOP_JOIN)
        c.execute(query, {"today": self.TODAY})
        return bool(c.fetchone()[0])

    def _cases(self):
        L = self.LINE
        return [
            ("L1 platform+shop+item", [self._P(platform="Shopee", shop="S1", item="ITM")], L, True),
            ("L2 platform+shop+sku", [self._P(platform="Shopee", shop="S1", seller_sku="SKU")], L, True),
            ("L3 platform+noshop+item", [self._P(platform="Shopee", shop="", item="ITM")], L, True),
            ("L4 platform+noshop+sku", [self._P(platform="Shopee", shop=None, seller_sku="SKU")], L, True),
            ("L5 All+item", [self._P(platform="All", shop="", item="ITM")], L, True),
            ("L5 All+sku", [self._P(platform="All", shop=None, seller_sku="SKU")], L, True),
            ("L6 fallback same platform", [self._P(is_brand_fallback=1, platform="Shopee")], L, True),
            ("L6 fallback All", [self._P(is_brand_fallback=1, platform="All")], L, True),
            ("eff_from==today inclusive", [self._P(platform="Shopee", shop="S1", item="ITM", effective_from=self.TODAY)], L, True),
            ("eff_to==today inclusive", [self._P(platform="Shopee", shop="S1", item="ITM", effective_to=self.TODAY)], L, True),
            ("future effective_from", [self._P(platform="Shopee", shop="S1", item="ITM", effective_from=self.TMRW)], L, False),
            ("expired effective_to", [self._P(platform="Shopee", shop="S1", item="ITM", effective_to=self.YDAY)], L, False),
            ("Draft", [self._P(status="Draft", platform="Shopee", shop="S1", item="ITM")], L, False),
            ("Inactive", [self._P(status="Inactive", platform="Shopee", shop="S1", item="ITM")], L, False),
            ("wrong shop (specific)", [self._P(platform="Shopee", shop="S2", item="ITM")], L, False),
            ("wrong platform", [self._P(platform="Lazada", shop="", item="ITM")], L, False),
            ("fallback wrong platform", [self._P(is_brand_fallback=1, platform="Lazada")], L, False),
            ("different brand", [self._P(brand="OTHER", platform="Shopee", shop="S1", item="ITM")], L, False),
            ("no policies", [], L, False),
            ("specific-shop sku, order other shop",
             [self._P(platform="Shopee", shop="S1", seller_sku="SKU")], dict(L, shop="S2"), False),
            ("noshop sku, order other shop (L4)",
             [self._P(platform="Shopee", shop="", seller_sku="SKU")], dict(L, shop="S2"), True),
            ("line sku-only, policy item-only",
             [self._P(platform="Shopee", shop="", item="ITM")], dict(L, item=None), False),
            ("All+item but policy has a shop",
             [self._P(platform="All", shop="S1", item="ITM")], L, False),
        ]

    def test_covered_iff_find_policy_hit(self):
        # SANITY GATE (before the equivalence loop): a broken stub that returns
        # (None, None) for everything would let every NEGATIVE case pass and hide
        # the real result. Prove the stub actually resolves a known L1 fixture to
        # a policy at level 1 first, so the 23-case equivalence below is trusted.
        self._pol = [self._P(platform="Shopee", shop="S1", item="ITM")]
        sdoc, slevel = self._mod.find_policy("B", "Shopee", "S1", "ITM", "SKU")
        self.assertIsNotNone(sdoc, "sanity: known L1 fixture must resolve via find_policy")
        self.assertEqual(slevel, 1, "sanity: known L1 fixture must resolve at level 1 (L1)")

        for label, policies, line, expect in self._cases():
            with self.subTest(label):
                # feed find_policy the SAME rows the SQL side sees (find_policy's
                # get_all mock reads self._pol; without this it stays [] from
                # setUp and every positive case wrongly returns (None, None)).
                self._pol = list(policies)
                doc, level = self._mod.find_policy(
                    line["brand"], line["platform"], line.get("shop"),
                    line.get("item"), line.get("seller_sku"))
                found = doc is not None
                covered = self._covered_sql(policies, line)
                self.assertEqual(
                    covered, found,
                    "%s: SQL covered=%s != find_policy hit=%s (level=%s)"
                    % (label, covered, found, level))
                self.assertEqual(found, expect, "%s: find_policy=%s expected=%s"
                                 % (label, found, expect))

    def test_brand_resolution_via_shop_mapping(self):
        """Explicit coverage for the COALESCE(NULLIF(ol.brand,''), s.brand)
        resolution that the 23-case equivalence never exercises (its line.brand
        is always populated). brand B is the covered brand throughout."""
        L = dict(self.LINE, shop="S1")     # Shopee / shop S1 / item ITM / sku SKU
        covering = [self._P(platform="Shopee", shop="S1", item="ITM")]   # brand B
        OMI = "OMI-1"

        # (a) populated ol.brand WINS over the shop mapping.
        line_a = dict(L, brand="B", omisell_shop_id=OMI)
        map_wrong = [{"omisell_shop_id": OMI, "brand": "OTHER", "status": "Active"}]
        self.assertTrue(self._covered_sql(covering, line_a, map_wrong),
                        "ol.brand=B must win over an OTHER shop mapping")
        self.assertFalse(
            self._covered_sql([self._P(brand="OTHER", platform="Shopee",
                                       shop="S1", item="ITM")], line_a, map_wrong),
            "resolved brand is B -> an OTHER-brand policy must NOT cover it")

        # (b) NULL / blank ol.brand + ACTIVE mapping resolves via the shop.
        map_ok = [{"omisell_shop_id": OMI, "brand": "B", "status": "Active"}]
        for blank in ("", None):
            line_b = dict(L, brand=blank, omisell_shop_id=OMI)
            self.assertTrue(self._covered_sql(covering, line_b, map_ok),
                            "blank ol.brand %r + Active mapping must resolve to B" % (blank,))

        # (c) blank ol.brand + NO matching mapping stays UNRESOLVED (not covered).
        line_c = dict(L, brand="", omisell_shop_id=OMI)
        self.assertFalse(self._covered_sql(covering, line_c, []),
                         "no shop mapping -> resolved brand NULL -> not covered")
        self.assertFalse(
            self._covered_sql(covering, line_c,
                              [{"omisell_shop_id": "OTHER-OMI", "brand": "B", "status": "Active"}]),
            "mapping for a different omisell_shop_id must not resolve")

        # (d) blank ol.brand + INACTIVE mapping stays UNRESOLVED (not covered).
        map_inactive = [{"omisell_shop_id": OMI, "brand": "B", "status": "Inactive"}]
        self.assertFalse(self._covered_sql(covering, line_c, map_inactive),
                         "Inactive shop mapping must not resolve the brand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
