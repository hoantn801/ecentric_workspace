"""fix/order-log-brand-backfill (2026-06-14): brand resolution + backfill.

Both layers run WITHOUT a bench/DB by routing the REAL SQL of
services.policy_coverage and patches.p005 through an in-memory SQLite (a
test-only renderer substitutes frappe's %(name)s params, incl. IN-tuples). So
the actual COALESCE / shop-join / EXISTS guard / correlated-subquery UPDATE are
exercised, not a re-implementation.

    bench run-tests --module ecentric_workspace.alerts.tests.test_order_log_brand_backfill
"""
import re
import sqlite3
import sys
import types
import unittest


class _AttrDict(dict):
    __getattr__ = dict.get


def _install_stub_frappe():
    if "frappe" in sys.modules and not getattr(sys.modules["frappe"], "_ec_stub", False):
        return sys.modules["frappe"], False
    f = types.ModuleType("frappe")
    f._ec_stub = True
    f.conf = {}
    f.db = types.SimpleNamespace(sql=lambda *a, **k: [], commit=lambda: None)
    u = types.ModuleType("frappe.utils")
    u.add_days = lambda d, n: "2026-05-15"      # since-window start (fixed)
    u.nowdate = lambda: "2026-06-14"            # today (fixed)
    f.utils = u
    sys.modules["frappe"] = f
    sys.modules["frappe.utils"] = u
    return f, True


_FK, _IS_STUB = _install_stub_frappe()
from ecentric_workspace.alerts.services import policy_coverage as pc   # noqa: E402
from ecentric_workspace.alerts.patches import p005_backfill_order_log_brand_from_shop as p005  # noqa: E402


def _render(query, params):
    """Test-only: inline-substitute frappe %(name)s params into literal SQL
    (handles strings, numbers, None, and IN-tuples). Fixtures only - no user
    input - so literal interpolation is safe here."""
    params = params or {}

    def lit(v):
        if v is None:
            return "NULL"
        if isinstance(v, (list, tuple)):
            return "(" + ",".join(lit(x) for x in v) + ")"
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    return re.sub(r"%\((\w+)\)s", lambda m: lit(params[m.group(1)]), query)


@unittest.skipUnless(_IS_STUB, "runs on the stubbed-frappe + sqlite harness")
class _SqliteHarness(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        c = self.conn.cursor()
        c.execute("CREATE TABLE `tabEC Marketplace Order Log` (name TEXT, brand TEXT, "
                  "omisell_shop_id TEXT, platform TEXT, shop TEXT, order_datetime TEXT)")
        c.execute("CREATE TABLE `tabEC Marketplace Order Item` (parent TEXT, seller_sku TEXT, "
                  "item TEXT, product_name TEXT, list_price REAL)")
        c.execute("CREATE TABLE `tabEC Marketplace Shop` (name TEXT, omisell_shop_id TEXT, "
                  "brand TEXT, status TEXT)")
        c.execute("CREATE TABLE `tabEC Price Policy` (name TEXT, brand TEXT, status TEXT, "
                  "platform TEXT, shop TEXT, item TEXT, seller_sku TEXT, is_brand_fallback INT, "
                  "effective_from TEXT, effective_to TEXT)")
        self.conn.commit()

        def sql(query, values=None, as_dict=False):
            cur = self.conn.execute(_render(query, values))
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            return [_AttrDict(zip(cols, row)) for row in cur.fetchall()]

        _FK.db.sql = sql
        _FK.db.commit = self.conn.commit
        _FK.conf = {}

    def tearDown(self):
        self.conn.close()

    # ---- fixture helpers ----
    def add_log(self, name, brand, shop_id, platform="TikTok", shop=None,
                dt="2026-06-10 09:00:00"):
        self.conn.execute(
            "INSERT INTO `tabEC Marketplace Order Log` VALUES (?,?,?,?,?,?)",
            (name, brand, shop_id, platform, shop, dt))

    def add_item(self, parent, seller_sku, item=None, product_name="P", list_price=0):
        self.conn.execute(
            "INSERT INTO `tabEC Marketplace Order Item` VALUES (?,?,?,?,?)",
            (parent, seller_sku, item, product_name, list_price))

    def add_shop(self, name, shop_id, brand, status="Active"):
        self.conn.execute(
            "INSERT INTO `tabEC Marketplace Shop` VALUES (?,?,?,?)",
            (name, shop_id, brand, status))
        self.conn.commit()

    def log_brand(self, name):
        return self.conn.execute(
            "SELECT brand FROM `tabEC Marketplace Order Log` WHERE name=?", (name,)
        ).fetchone()[0]


class TestCoverageBrandResolution(_SqliteHarness):
    """policy_coverage attributes order SKUs by RESOLVED brand. No price policies
    -> every order SKU is 'missing', so missing_counts shows the attribution."""

    def test_null_brand_active_mapping_attributed_to_mapped_brand(self):
        self.add_log("OL1", None, "34591")
        self.add_item("OL1", "SKU-A")
        self.add_shop("SH-LOF", "34591", "LOF-VN", status="Active")
        self.assertEqual(pc.missing_counts(None), {"LOF-VN": 1})

    def test_null_brand_no_mapping_excluded(self):
        self.add_log("OL1", None, "99999")        # no shop row for 99999
        self.add_item("OL1", "SKU-A")
        self.add_log("OL2", None, None)            # no shop id at all
        self.add_item("OL2", "SKU-B")
        self.assertEqual(pc.missing_counts(None), {})   # excluded, no null bucket

    def test_null_brand_inactive_mapping_excluded(self):
        self.add_log("OL1", None, "29571")
        self.add_item("OL1", "SKU-A")
        self.add_shop("SH-FES", "29571", "FES-VN", status="Inactive")
        self.assertEqual(pc.missing_counts(None), {})

    def test_existing_brand_not_overridden_by_mapping(self):
        self.add_log("OL1", "BBT-VN", "34591")     # own brand set...
        self.add_item("OL1", "SKU-A")
        self.add_shop("SH-LOF", "34591", "LOF-VN", status="Active")  # ...maps elsewhere
        self.assertEqual(pc.missing_counts(None), {"BBT-VN": 1})     # own brand wins

    def test_scoped_query_uses_resolved_brand(self):
        # brand-scoped path (missing_count -> IN (...)) must match on resolved brand
        self.add_log("OL1", None, "34591")
        self.add_item("OL1", "SKU-A")
        self.add_shop("SH-LOF", "34591", "LOF-VN", status="Active")
        self.assertEqual(pc.missing_count("LOF-VN"), 1)
        self.assertEqual(pc.missing_count("OTHER"), 0)

    def test_covered_sku_resolved_brand_not_missing(self):
        # an Active policy for the RESOLVED brand must mark the SKU covered
        self.add_log("OL1", None, "34591", platform="TikTok")
        self.add_item("OL1", "SKU-A")
        self.add_shop("SH-LOF", "34591", "LOF-VN", status="Active")
        self.conn.execute(
            "INSERT INTO `tabEC Price Policy` VALUES "
            "('PP1','LOF-VN','Active','TikTok','',NULL,'SKU-A',0,NULL,NULL)")
        self.conn.commit()
        self.assertEqual(pc.missing_counts(None), {})   # covered -> not missing


class TestBackfillPatch(_SqliteHarness):
    def _seed(self):
        self.add_log("OL1", None, "34591")            # NULL + active map -> set
        self.add_log("OL2", "", "34591")              # blank + active map -> set
        self.add_log("OL3", None, "99999")            # NULL + no map -> skip
        self.add_log("OL4", None, "29571")            # NULL + inactive map -> skip
        self.add_log("OL5", "BBT-VN", "34591")        # populated -> never overwrite
        self.add_log("OL6", None, None)               # no shop id -> skip
        self.add_shop("SH-LOF", "34591", "LOF-VN", status="Active")
        self.add_shop("SH-FES", "29571", "FES-VN", status="Inactive")
        self.conn.commit()

    def test_backfill_sets_only_eligible_and_reports(self):
        self._seed()
        res = p005.execute()
        self.assertEqual(res["updated"], 2)                     # OL1 + OL2
        self.assertEqual(res["by_brand"], {"SH-LOF|LOF-VN": 2})
        self.assertEqual(self.log_brand("OL1"), "LOF-VN")
        self.assertEqual(self.log_brand("OL2"), "LOF-VN")
        self.assertIsNone(self.log_brand("OL3"))               # no map -> untouched
        self.assertIsNone(self.log_brand("OL4"))               # inactive -> untouched
        self.assertEqual(self.log_brand("OL5"), "BBT-VN")      # NOT overridden
        self.assertIsNone(self.log_brand("OL6"))               # no shop id -> untouched

    def test_rerun_is_no_op(self):
        self._seed()
        p005.execute()
        res2 = p005.execute()
        self.assertEqual(res2, {"updated": 0, "by_brand": {}})

    def test_no_rows_deleted(self):
        self._seed()
        before = self.conn.execute(
            "SELECT COUNT(*) FROM `tabEC Marketplace Order Log`").fetchone()[0]
        p005.execute()
        after = self.conn.execute(
            "SELECT COUNT(*) FROM `tabEC Marketplace Order Log`").fetchone()[0]
        self.assertEqual(before, after)


def _src(rel):
    import os
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestPatchSourceGuards(unittest.TestCase):
    def test_patch_no_hard_delete_no_overwrite(self):
        s = _src("patches/p005_backfill_order_log_brand_from_shop.py")
        self.assertNotIn("frappe.db.delete", s)
        self.assertNotIn("DELETE FROM", s.upper())
        # only NULL/'' targeted -> a populated brand is never overwritten
        self.assertIn("brand IS NULL", s)
        self.assertIn("status = 'Active'", s)

    def test_patch_registered_once(self):
        txt = _src("../patches.txt")
        self.assertEqual(
            txt.count("ecentric_workspace.alerts.patches.p005_backfill_order_log_brand_from_shop"),
            1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
