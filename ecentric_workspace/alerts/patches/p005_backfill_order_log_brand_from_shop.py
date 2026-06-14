"""Backfill EC Marketplace Order Log.brand from the Active shop mapping (2026-06-14).

Orders ingested before their shop->brand mapping existed were stored with a
NULL/blank brand: ingestion resolves brand ONCE at ingest (brand_resolver) and
never re-resolves, and re-pulls are idempotent (skip re-resolution). This sets
brand at the SOURCE from the now-Active EC Marketplace Shop mapping, so every
consumer (policy_coverage, dashboard KPIs, baseline medians, api_brands counts,
missing_brand_mapping noise) attributes the orders to the correct brand.

Properties:
  * Touches ONLY logs whose brand IS NULL or '' - a populated brand is NEVER
    overwritten (the WHERE guarantees it).
  * Resolves ONLY via an Active EC Marketplace Shop whose brand is non-blank,
    matching brand_resolver.resolve_brand's shop path. NO hardcoded shop/brand.
  * Portable correlated-subquery UPDATE (MySQL + SQLite) with an EXISTS guard, so
    a row is only set when a qualifying mapping exists (never set to NULL).
  * IDEMPOTENT: after the first run the affected logs are no longer NULL/blank, so
    a re-run matches 0 rows -> no-op.
  * Reports affected logs grouped by (shop, brand). No hard delete, no item
    change, sync_status untouched. Raw UPDATE (no per-row controller hooks) is
    intentional - brand is a plain attribute with no lifecycle/audit dependency,
    and a bulk data-correction must not emit thousands of Version rows.

Rollback: a code revert does NOT un-set the backfilled brands (conservative,
NULL->mapped only). To revert the data, restore EC Marketplace Order Log from a
pre-patch backup - re-nulling is not recommended.
"""
import frappe

# Same predicate used by the SELECT preview, the EXISTS guard and the subquery:
# an Active shop, mapped by omisell_shop_id, with a non-blank brand.
_MAP = (
    "FROM `tabEC Marketplace Shop` s "
    "WHERE s.omisell_shop_id = `tabEC Marketplace Order Log`.omisell_shop_id "
    "AND s.status = 'Active' AND s.brand IS NOT NULL AND s.brand != ''"
)
_TARGET = ("(`tabEC Marketplace Order Log`.brand IS NULL "
           "OR `tabEC Marketplace Order Log`.brand = '') "
           "AND `tabEC Marketplace Order Log`.omisell_shop_id IS NOT NULL "
           "AND `tabEC Marketplace Order Log`.omisell_shop_id != ''")


def _preview():
    """Logs that WILL be backfilled, grouped by (shop, brand). Read-only."""
    return frappe.db.sql(
        "SELECT s.brand AS brand, s.name AS shop, COUNT(*) AS n "
        "FROM `tabEC Marketplace Order Log` "
        "JOIN `tabEC Marketplace Shop` s "
        "  ON s.omisell_shop_id = `tabEC Marketplace Order Log`.omisell_shop_id "
        " AND s.status = 'Active' AND s.brand IS NOT NULL AND s.brand != '' "
        "WHERE (`tabEC Marketplace Order Log`.brand IS NULL "
        "       OR `tabEC Marketplace Order Log`.brand = '') "
        "  AND `tabEC Marketplace Order Log`.omisell_shop_id IS NOT NULL "
        "  AND `tabEC Marketplace Order Log`.omisell_shop_id != '' "
        "GROUP BY s.brand, s.name", as_dict=True)


def execute():
    preview = _preview()
    if not preview:
        print("p005_backfill_order_log_brand_from_shop: 0 NULL-brand logs with an "
              "Active shop mapping - no-op")
        return {"updated": 0, "by_brand": {}}

    frappe.db.sql(
        "UPDATE `tabEC Marketplace Order Log` "
        "SET brand = (SELECT s.brand " + _MAP + " LIMIT 1) "
        "WHERE " + _TARGET + " AND EXISTS (SELECT 1 " + _MAP + ")")
    frappe.db.commit()

    by_brand, total = {}, 0
    for r in preview:
        by_brand["%s|%s" % (r["shop"], r["brand"])] = r["n"]
        total += int(r["n"])
    print("p005_backfill_order_log_brand_from_shop: set brand on %d log(s): %s"
          % (total, by_brand))
    return {"updated": total, "by_brand": by_brand}
