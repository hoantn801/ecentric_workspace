"""search_skus fix tests (2026-06-12) - LOF GBS_LOF_8936025777042-48 incident.

Bug: caller sent `q=`; the old signature only knew `keyword` -> q silently
ignored -> unfiltered top-N brand rows returned ("unrelated rows").

Covers REQs: q aliases honored; exact q returns exact SKU first; partial q
returns only matching SKUs; no-match q -> []; brand scope enforced.

Runs anywhere (frappe stub + monkeypatched get_all/perms).
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_sku_search
"""
import os
import re
import sys
import types
import unittest
from datetime import datetime


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.ValidationError = type("ValidationError", (Exception,), {})
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f._ = lambda s: s
    f.conf = types.SimpleNamespace(get=lambda *a, **k: None)
    f.throw = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
    f.log_error = lambda *a, **k: None
    f.session = types.SimpleNamespace(user="Administrator")
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.add_to_date = lambda d, **k: d
    fu.get_datetime = lambda v: v
    fu.now_datetime = lambda: datetime(2026, 6, 12)
    fu.nowdate = lambda: "2026-06-12"
    fu.add_days = lambda *a, **k: "2026-01-01"
    fu.cint = lambda v: int(v or 0)
    fu.flt = lambda v, *a: float(v or 0)
    sys.modules["frappe.utils"] = fu


_stub_frappe()
from ecentric_workspace.alerts import api_sku_catalog as api

TARGET = "GBS_LOF_8936025777042-48"

CATALOG = [  # newest-first, mimics order_by last_seen_at desc
    {"seller_sku": "LOF-OTHER-1", "product_name": "Banh gao khac"},
    {"seller_sku": "GBS_LOF_8936025777042-12", "product_name": "Kun Ly Lac 12 ly"},
    {"seller_sku": TARGET, "product_name": "Kun Ly Lac 48 ly 1 THUNG"},
    {"seller_sku": "LOF-XX", "product_name": "Combo GBS_LOF_8936025777042-48 thung"},
    {"seller_sku": "LOF-NAME-ONLY", "product_name": "Xuc xich Kun pho mai"},
]


def _sql_like(pattern, value):
    """REAL SQL LIKE semantics: '%' = any run, '_' = any ONE char."""
    rx = "^" + "".join(
        ".*" if ch == "%" else "." if ch == "_" else re.escape(ch)
        for ch in pattern) + "$"
    return re.match(rx, value or "", re.IGNORECASE) is not None


class _FakeGetAll:
    """Mimics frappe.get_all incl. real LIKE wildcards in or_filters - so the
    endpoint's literal re-check is actually exercised by '_' false hits."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, doctype, filters=None, or_filters=None, fields=None,
                 order_by=None, page_length=20, **k):
        self.calls.append({"filters": filters, "or_filters": or_filters,
                           "page_length": page_length})
        out = []
        for r in self.rows:
            if or_filters:
                pat = or_filters[0][2]
                if not (_sql_like(pat, r["seller_sku"]) or
                        _sql_like(pat, r["product_name"])):
                    continue
            out.append(dict(r, rsp_price=1, platform="TikTok", shop=None,
                            omisell_shop_id="34591", source_level="omisell_product"))
        return out[:page_length]


class TestRankPure(unittest.TestCase):
    def test_rank_levels(self):
        self.assertEqual(api.rank_sku_match(TARGET, TARGET, "x"), 0)
        self.assertEqual(api.rank_sku_match(TARGET.lower(), TARGET, "x"), 0)
        self.assertEqual(api.rank_sku_match("8936025777042", TARGET, "x"), 1)
        self.assertEqual(api.rank_sku_match("Kun", "OTHER", "Kun Ly Lac"), 2)
        self.assertEqual(api.rank_sku_match("zzz", "OTHER", "name"), 3)
        self.assertEqual(api.rank_sku_match("", "OTHER", "name"), 3)

    def test_resolve_aliases(self):
        self.assertEqual(api.resolve_search_query(q="A"), "A")
        self.assertEqual(api.resolve_search_query(query=" B "), "B")
        self.assertEqual(api.resolve_search_query(search="C"), "C")
        self.assertEqual(api.resolve_search_query(keyword="D"), "D")
        self.assertEqual(api.resolve_search_query(q=None, query="", search="C",
                                                  keyword="D"), "C")
        self.assertEqual(api.resolve_search_query(), "")


class TestSearchEndpoint(unittest.TestCase):
    def setUp(self):
        self._get_all = getattr(api.frappe, "get_all", None)
        self._perm = api.perms.require_brand_access
        self.fake = _FakeGetAll(CATALOG)
        api.frappe.get_all = self.fake
        self.perm_calls = []
        api.perms.require_brand_access = lambda user, brand: self.perm_calls.append(brand)

    def tearDown(self):
        if self._get_all is not None:
            api.frappe.get_all = self._get_all
        api.perms.require_brand_access = self._perm

    def test_exact_q_returns_exact_sku_first(self):
        res = api.search_skus("LOF-VN", q=TARGET)
        skus = [r["seller_sku"] for r in res["rows"]]
        self.assertEqual(skus[0], TARGET)               # exact ranked first
        self.assertIn("LOF-XX", skus)                   # name-match after
        self.assertLess(skus.index(TARGET), skus.index("LOF-XX"))

    def test_partial_q_only_matching_rows(self):
        res = api.search_skus("LOF-VN", q="8936025777042")
        skus = [r["seller_sku"] for r in res["rows"]]
        self.assertEqual(set(skus), {"GBS_LOF_8936025777042-12", TARGET, "LOF-XX"})
        # SKU-partial (rank 1) before name-only match (rank 2)
        self.assertLess(skus.index("GBS_LOF_8936025777042-12"), skus.index("LOF-XX"))
        self.assertNotIn("LOF-OTHER-1", skus)
        self.assertNotIn("LOF-NAME-ONLY", skus)

    def test_query_and_search_aliases_work(self):
        for kwargs in ({"query": TARGET}, {"search": TARGET}, {"keyword": TARGET}):
            res = api.search_skus("LOF-VN", **kwargs)
            self.assertEqual(res["rows"][0]["seller_sku"], TARGET, kwargs)

    def test_no_match_returns_empty(self):
        res = api.search_skus("LOF-VN", q="NO-SUCH-SKU-999")
        self.assertEqual(res["rows"], [])

    def test_brand_scope_enforced(self):
        api.search_skus("LOF-VN", q=TARGET)
        self.assertEqual(self.perm_calls, ["LOF-VN"])
        flt = self.fake.calls[-1]["filters"]
        self.assertIn(["brand", "=", "LOF-VN"], flt)

    def test_literal_recheck_drops_sql_wildcard_false_hits(self):
        """q contains '_' (SQL LIKE wildcard). GBSxLOFx... LIKE-matches the
        pattern but is NOT a literal containment -> must be dropped."""
        rows = CATALOG + [{"seller_sku": "GBSxLOFx8936025777042-48",
                           "product_name": "false like hit"}]
        api.frappe.get_all = _FakeGetAll(rows)
        res = api.search_skus("LOF-VN", q=TARGET)
        skus = [r["seller_sku"] for r in res["rows"]]
        self.assertNotIn("GBSxLOFx8936025777042-48", skus)
        self.assertIn(TARGET, skus)


def _src():
    path = os.path.join(os.path.dirname(__file__), "..", "api_sku_catalog.py")
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestWiring(unittest.TestCase):
    def test_no_touch_constraints(self):
        s = _src()
        self.assertIn("def resolve_search_query", s)
        self.assertIn("def rank_sku_match", s)
        self.assertIn("perms.require_brand_access(frappe.session.user, brand)", s)
        for banned in ("OmisellClient", "pull_recent", "scheduler"):
            self.assertNotIn(banned, s)


if __name__ == "__main__":
    unittest.main()
