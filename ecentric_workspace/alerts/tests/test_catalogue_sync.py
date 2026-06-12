"""G2.2 catalogue sync tests (2026-06-12).

REQ: parent rows, variant rows, shop-scoped keys, price-mismatch guard,
preview-no-write. Pure parts run anywhere; upsert/endpoints are covered by
source-text safety asserts (frappe-dependent paths run on bench).

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_catalogue_sync
"""
import os
import sys
import types
import unittest
from datetime import datetime


def _stub_frappe():
    """sku_catalog imports frappe at module top; stub it for pure runs
    (one stub per process - keep the attr UNION sibling tests rely on)."""
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
from ecentric_workspace.alerts.services import catalogue_sync as cs

RAW = {
    "catalogue_id": "CAT-1", "sku": "P02056",
    "name": "Tui Ca phe Pho Sua Da", "price": 247000, "price_sale": 222300,
    "images": ["https://img.example/x.jpg", "https://img.example/y.jpg"],
    "platform": "lazada", "shop_id": 21612, "shop_name": "FES-VN-LAZADA",
    "external_id": "EXT-9", "status": 1, "status_name": "active",
    "external_stock": 55,
    "variants": [
        {"sku": "P02056-V1", "name": "Variant 30 goi", "price": 250000,
         "price_sale": 230000, "external_id": "EXT-9-V1", "external_stock": 5},
        {"sku": "", "name": "no-sku variant ignored"},
        {"sku": "P02056-V2"},   # inherits parent fields
    ],
}


class TestNormalizeFlatten(unittest.TestCase):
    def test_parent_row(self):
        rows = cs.normalize_catalogue(RAW)
        p = rows[0]
        self.assertEqual(p["seller_sku"], "P02056")
        self.assertEqual(p["is_variant"], 0)
        self.assertEqual(p["platform"], "Lazada")          # normalized
        self.assertEqual(p["platform_raw"], "lazada")      # raw kept
        self.assertEqual(p["omisell_shop_id"], "21612")
        self.assertEqual(p["external_product_id"], "EXT-9")
        self.assertEqual(p["catalogue_id"], "CAT-1")
        self.assertEqual(p["price"], 247000.0)
        self.assertEqual(p["price_sale"], 222300.0)
        self.assertEqual(p["image_url"], "https://img.example/x.jpg")

    def test_variant_rows_flattened(self):
        rows = cs.normalize_catalogue(RAW)
        self.assertEqual(len(rows), 3)  # parent + V1 + V2 (empty-sku dropped)
        v1, v2 = rows[1], rows[2]
        self.assertEqual(v1["seller_sku"], "P02056-V1")
        self.assertEqual(v1["is_variant"], 1)
        self.assertEqual(v1["parent_sku"], "P02056")
        self.assertEqual(v1["parent_catalogue_id"], "CAT-1")
        self.assertEqual(v1["price"], 250000.0)            # own price wins
        self.assertEqual(v1["external_product_id"], "EXT-9-V1")
        # V2 has only a sku -> inherits parent fields
        self.assertEqual(v2["seller_sku"], "P02056-V2")
        self.assertEqual(v2["price"], 247000.0)
        self.assertEqual(v2["product_name"], RAW["name"])
        self.assertEqual(v2["omisell_shop_id"], "21612")

    def test_parent_without_sku_variants_still_synced(self):
        raw = dict(RAW, sku="")
        rows = cs.normalize_catalogue(raw)
        self.assertEqual([r["seller_sku"] for r in rows],
                         ["P02056-V1", "P02056-V2"])
        self.assertTrue(all(r["is_variant"] for r in rows))

    def test_platform_normalization(self):
        """Blocker fix 2026-06-12: FES preview had platform_raw='shopee_v2'
        normalized to 'Other'. Aliases/prefixes must map to the Select value."""
        for raw, want in (("shopee", "Shopee"), ("shopee_v2", "Shopee"),
                          ("shopee-v2", "Shopee"), ("SHOPEE_V2", "Shopee"),
                          ("Lazada", "Lazada"), ("lazada_v2", "Lazada"),
                          ("TIKTOK", "TikTok"), ("tiktok_shop", "TikTok"),
                          ("tiktok-v2", "TikTok"),
                          ("amazon", "Other"), ("", "Other"), (None, "Other")):
            self.assertEqual(cs.norm_platform(raw), want, raw)

    def test_platform_v2_rows_normalize_in_full_row(self):
        raw = dict(RAW, platform="shopee_v2")
        rows = cs.normalize_catalogue(raw)
        self.assertTrue(all(r["platform"] == "Shopee" for r in rows))
        self.assertTrue(all(r["platform_raw"] == "shopee_v2" for r in rows))


class TestShopScopedKeys(unittest.TestCase):
    def test_same_sku_different_shop_distinct_keys(self):
        from ecentric_workspace.alerts.services import sku_catalog as sc
        a = sc.catalog_key("Omisell", "21611", "P02056")  # Shopee shop
        b = sc.catalog_key("Omisell", "21612", "P02056")  # Lazada shop
        self.assertNotEqual(a, b)
        self.assertEqual(a, sc.catalog_key("Omisell", "21611", "P02056"))


class TestPriceGuard(unittest.TestCase):
    def test_match_within_tolerance(self):
        self.assertEqual(cs.compare_price(247000, 247000), "match")
        self.assertEqual(cs.compare_price(247900, 247000), "match")   # <0.5%
        self.assertEqual(cs.compare_price(250500, 247000), "mismatch")

    def test_no_reference(self):
        self.assertEqual(cs.compare_price(247000, None), "no_reference")
        self.assertEqual(cs.compare_price(247000, 0), "no_reference")

    def test_missing_catalogue_price_is_mismatch(self):
        self.assertEqual(cs.compare_price(None, 247000), "mismatch")

    def test_note_carries_confidence_and_extras(self):
        rows = cs.normalize_catalogue(RAW)
        note = cs.build_note(rows[1], "low")
        import json
        d = json.loads(note)
        self.assertEqual(d["price_confidence"], "low")
        self.assertEqual(d["src"], "catalogue/list")
        self.assertEqual(d["parent_sku"], "P02056")
        self.assertEqual(d["is_variant"], 1)
        self.assertLessEqual(len(note), cs.NOTE_MAX)

    def test_hash_changes_with_price_and_confidence_inputs(self):
        rows = cs.normalize_catalogue(RAW)
        h1 = cs.row_hash(rows[0])
        r2 = dict(rows[0], price=999.0)
        self.assertNotEqual(h1, cs.row_hash(r2))
        self.assertEqual(h1, cs.row_hash(dict(rows[0])))


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestSafetyWiring(unittest.TestCase):
    def test_preview_never_writes(self):
        """REQ: preview must not write - no insert/save/set_value anywhere
        in api_catalogue_sync (writes live ONLY in services.catalogue_sync,
        called from confirm)."""
        s = _src("api_catalogue_sync.py")
        for banned in (".insert(", ".save(", "set_value", "delete_doc"):
            self.assertNotIn(banned, s)
        self.assertIn("def preview_catalogue_sku_sync", s)
        self.assertIn("upsert_catalogue_row", s.split("def confirm_catalogue_sku_sync")[1])
        self.assertNotIn("upsert_catalogue_row",
                         s.split("def preview_catalogue_sku_sync")[1]
                         .split("def confirm_catalogue_sku_sync")[0])

    def test_confirm_writes_only_sku_catalog(self):
        svc = _src("services/catalogue_sync.py")
        # the ONLY doctype ever written:
        self.assertEqual(svc.count('"doctype": "EC Marketplace SKU Catalog"'), 1)
        for banned in ("EC Alert", "Order Log", "EC Brand Integration",
                       "delete_doc", "frappe.delete"):
            self.assertNotIn(banned, svc)

    def test_order_derived_rsp_wins(self):
        svc = _src("services/catalogue_sync.py")
        self.assertIn('existing.source_level == "order_derived" and existing.rsp_price', svc)
        self.assertIn("order-derived wins", svc)  # guard documented in-code

    def test_endpoints_sm_only_and_capped(self):
        s = _src("api_catalogue_sync.py")
        self.assertEqual(s.count('frappe.only_for("System Manager")'), 2)
        self.assertIn("TIME_BUDGET_SECONDS = 50", s)
        self.assertIn("resolve_confirm_params", s)

    def test_client_method_read_only_path(self):
        s = _src("services/omisell_client.py")
        self.assertIn('"GET", "/api/v2/public/catalogue/list"', s)
        self.assertIn("def get_catalogues(self, page=1, page_size=50):", s)


class TestConfirmParamResolution(unittest.TestCase):
    """Bad Gateway hotfix 2026-06-12: confirm must honor ALL caller alias
    params, clamp to sync-safe bounds, and echo effective values."""

    def test_defaults_sync_safe(self):
        p = cs.resolve_confirm_params()
        self.assertEqual(p["effective_pages_requested"], 2)
        self.assertEqual(p["effective_row_cap"], 300)
        self.assertEqual(p["effective_page_size"], 50)
        self.assertEqual(p["start_page"], 1)
        self.assertFalse(p["allow_heavy"])

    def test_honors_pages_requested_alias(self):
        self.assertEqual(cs.resolve_confirm_params(pages_requested=3)
                         ["effective_pages_requested"], 3)

    def test_honors_max_pages_alias(self):
        self.assertEqual(cs.resolve_confirm_params(max_pages=4)
                         ["effective_pages_requested"], 4)

    def test_honors_row_cap_alias(self):
        self.assertEqual(cs.resolve_confirm_params(row_cap=300)
                         ["effective_row_cap"], 300)

    def test_honors_limit_alias(self):
        self.assertEqual(cs.resolve_confirm_params(limit=120)
                         ["effective_row_cap"], 120)

    def test_alias_precedence_first_non_empty(self):
        p = cs.resolve_confirm_params(pages=None, max_pages="", pages_requested=3,
                                      max_rows=None, row_cap=250, limit=999)
        self.assertEqual(p["effective_pages_requested"], 3)
        self.assertEqual(p["effective_row_cap"], 250)

    def test_hard_sync_page_cap_unless_heavy(self):
        self.assertEqual(cs.resolve_confirm_params(pages=40)
                         ["effective_pages_requested"], 5)      # capped
        self.assertEqual(cs.resolve_confirm_params(pages=40, allow_heavy=1)
                         ["effective_pages_requested"], 40)     # explicit
        self.assertEqual(cs.resolve_confirm_params(pages=99, allow_heavy="true")
                         ["effective_pages_requested"], 40)     # heavy ceiling

    def test_row_and_page_size_clamps(self):
        p = cs.resolve_confirm_params(limit=999999, page_size=500)
        self.assertEqual(p["effective_row_cap"], cs.CONFIRM_MAX_ROWS)
        self.assertEqual(p["effective_page_size"], cs.PAGE_SIZE_MAX)
        self.assertEqual(cs.resolve_confirm_params(page_size="garbage")
                         ["effective_page_size"], 50)           # fail-safe

    def test_start_page(self):
        self.assertEqual(cs.resolve_confirm_params(start_page=7)["start_page"], 7)
        self.assertEqual(cs.resolve_confirm_params(start_page=0)["start_page"], 1)


class TestConfirmTimeboxWiring(unittest.TestCase):
    """Timebox/resume behavior - source-level (endpoint needs bench to run)."""

    def test_confirm_echoes_effective_params(self):
        s = _src("api_catalogue_sync.py")
        body = s.split("def confirm_catalogue_sku_sync")[1]
        self.assertIn("resolve_confirm_params", body)
        self.assertIn("out = dict(p,", body)  # effective_* echoed into response

    def test_timebox_returns_partial_with_next_page(self):
        s = _src("api_catalogue_sync.py")
        body = s.split("def confirm_catalogue_sku_sync")[1]
        for marker in ('out["timeboxed"] = True', 'out["next_page"] = page',
                       'out["capped_at"]', 'out["rows_processed"] = processed'):
            self.assertIn(marker, body)
        # both fetch-phase and upsert-phase deadline checks exist
        self.assertEqual(body.count("time.monotonic() > deadline"), 2)

    def test_rerun_idempotency_documented_and_hash_gated(self):
        """Re-run never duplicates: upsert is hash-gated (created/enriched/
        unchanged) - the same row twice yields 'unchanged' the second time."""
        svc = _src("services/catalogue_sync.py")
        self.assertIn("existing.raw_payload_hash == h", svc)
        self.assertIn('return "unchanged"', svc)
        self.assertIn("start_page=next_page", _src("api_catalogue_sync.py"))


if __name__ == "__main__":
    unittest.main()
