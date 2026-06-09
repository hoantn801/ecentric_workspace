"""Phase G2.1 tests - SKU catalog key/hash (pure) + no-secret projection.

sku_catalog imports frappe at module top, so a minimal stub is installed first;
catalog_key / _row_hash / _fit are pure. Upsert/backfill are DB-dependent ->
bench-pending.
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_g2
"""
import sys
import types
import unittest


def _stub_frappe():
    try:
        import frappe  # noqa
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f._ = lambda s: s
    f.session = types.SimpleNamespace(user="Administrator")
    f.log_error = lambda *a, **k: None
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.add_days = lambda *a, **k: "2026-01-01"
    fu.now_datetime = lambda: "2026-06-08 00:00:00"
    fu.nowdate = lambda: "2026-06-08"
    fu.cint = lambda v: int(v or 0)
    sys.modules["frappe.utils"] = fu


_stub_frappe()
from ecentric_workspace.alerts.services import sku_catalog as sc


class TestCatalogKey(unittest.TestCase):
    def test_format_and_parts(self):
        k = sc.catalog_key("Omisell", "12345", "P02056")
        self.assertEqual(k, "Omisell|12345|P02056")

    def test_distinct_by_shop_and_sku(self):
        a = sc.catalog_key("Omisell", "1", "SKU")
        self.assertNotEqual(a, sc.catalog_key("Omisell", "2", "SKU"))   # diff shop
        self.assertNotEqual(a, sc.catalog_key("Omisell", "1", "SKU2"))  # diff sku
        self.assertNotEqual(a, sc.catalog_key("ERP", "1", "SKU"))       # diff source

    def test_stable(self):
        self.assertEqual(sc.catalog_key("Omisell", "1", " P1 "),
                         sc.catalog_key("Omisell", "1", "P1"))  # trims

    def test_none_parts(self):
        k = sc.catalog_key("Omisell", None, "P1")
        self.assertEqual(k, "Omisell||P1")

    def test_fit_140(self):
        long_sku = "X" * 300
        k = sc.catalog_key("Omisell", "shop", long_sku)
        self.assertLessEqual(len(k), 140)
        self.assertIn("#", k)  # hashed tail


class TestRowHash(unittest.TestCase):
    def test_changes_with_rsp(self):
        h1 = sc._row_hash("Product A", 282000, "Shopee", "FES-VN-SHOPEE")
        h2 = sc._row_hash("Product A", 250000, "Shopee", "FES-VN-SHOPEE")  # rsp change
        self.assertNotEqual(h1, h2)

    def test_stable_when_same(self):
        self.assertEqual(
            sc._row_hash("P", 100, "Shopee", "S"),
            sc._row_hash("P", 100, "Shopee", "S"))

    def test_changes_with_name(self):
        self.assertNotEqual(
            sc._row_hash("A", 100, "Shopee", "S"),
            sc._row_hash("B", 100, "Shopee", "S"))


class TestNoSecretInProjection(unittest.TestCase):
    def test_catalog_fields_have_no_secret(self):
        from ecentric_workspace.alerts import api_sku_catalog as api
        for secret in ("api_key", "api_secret", "token", "password"):
            self.assertNotIn(secret, api.CAT_FIELDS)


if __name__ == "__main__":
    unittest.main()
