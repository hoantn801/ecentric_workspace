"""Canonical price-policy COVERAGE source (2026-06-14).

missing_policy is a SETUP/COVERAGE gap, not an operational price alert. This is
the SINGLE source of truth for "which SKUs lack an active price policy", used by
ALL of:
  * api_policies.missing_policy_summary  (per-brand chip count)
  * api_sku_catalog.policy_missing_skus  (coverage modal list)
  * services.case_todo._remaining_missing_skus  (aggregated Setup ToDo)
so the chip count, the modal list and the ToDo can never disagree.

Definition (order-derived, scope + effective aware):
  A SKU is MISSING coverage if it appears in `EC Marketplace Order Item` joined
  to `EC Marketplace Order Log` within the window (default 30 days) AND there is
  NO active, in-effect `EC Price Policy` that policy_lookup.find_policy would
  return for that line's (brand, platform, shop, item, seller_sku). The
  NOT EXISTS predicate below mirrors the exact 6-level priority of
  policy_lookup.find_policy (existence, not order), so "covered" == "find_policy
  returns a policy". It is a SINGLE batched query (no N+1 across brands/SKUs).

Brand resolution (2026-06-14): rows are attributed by RESOLVED brand =
COALESCE(NULLIF(ol.brand,''), active_shop.brand) - the log's own brand, else the
Active EC Marketplace Shop mapping for its omisell_shop_id. Rows that resolve to
nothing (no own brand AND no Active mapping) are EXCLUDED from Price Setup and
remain handled by missing_brand_mapping; a populated ol.brand is never
overridden. (The p005 backfill fixes ol.brand at source; this is the query-time
safety net.)

Brand scope / permission are enforced by the API callers (this service takes a
brand list and trusts it).
"""
import frappe
from frappe.utils import add_days, nowdate

from . import exemption_guard

DEFAULT_WINDOW_DAYS = 30

# Resolved brand (2026-06-14): the order log's OWN brand wins; when it is NULL or
# blank (logs ingested before their shop->brand mapping existed - ingestion
# resolves brand once and never re-resolves) we fall back to the Active
# EC Marketplace Shop mapping for the same omisell_shop_id. Mirrors
# brand_resolver.resolve_brand's shop path. The p005 backfill fixes ol.brand at
# source; this keeps coverage correct in the gap and for any future
# ingest-before-mapping. A populated ol.brand is NEVER overridden by the mapping.
_RESOLVED_BRAND = "COALESCE(NULLIF(ol.brand, ''), s.brand)"

# Active, brand-bearing shop mapping joined by omisell_shop_id. LEFT JOIN, so a
# row whose shop is unmapped / Inactive / blank-brand resolves to NULL and is
# EXCLUDED from Price Setup (it stays handled by missing_brand_mapping) - never
# silently attributed to a wrong brand.
_SHOP_JOIN = (
    "LEFT JOIN `tabEC Marketplace Shop` s "
    "ON s.omisell_shop_id = ol.omisell_shop_id "
    "AND s.status = 'Active' AND s.brand IS NOT NULL AND s.brand != ''"
)

# Mirrors policy_lookup.find_policy EXISTENCE for a line (brand = resolved brand):
#   L1-L4  specific platform, shop-specific OR no-shop, item OR seller_sku
#   L5     platform 'All', no shop, item OR seller_sku
#   L6     is_brand_fallback, platform in (line.platform, 'All')
# An order line's platform is always set, so the find_policy "platform required
# for L1-L4" guard is implicitly satisfied.
_COVERED = (
    "EXISTS (SELECT 1 FROM `tabEC Price Policy` pp "
    "WHERE pp.brand = " + _RESOLVED_BRAND + " AND pp.status = 'Active' "
    "AND (pp.effective_from IS NULL OR pp.effective_from <= %(today)s) "
    "AND (pp.effective_to IS NULL OR pp.effective_to >= %(today)s) "
    "AND ( "
    "  ( (pp.seller_sku = oi.seller_sku OR pp.item = oi.item) AND ( "
    "        (pp.platform = ol.platform AND (pp.shop IS NULL OR pp.shop = '' OR pp.shop = ol.shop)) "
    "     OR (pp.platform = 'All' AND (pp.shop IS NULL OR pp.shop = '')) ) ) "
    "  OR ( pp.is_brand_fallback = 1 AND (pp.platform = ol.platform OR pp.platform = 'All') ) "
    ") )"
)


def window_days(days=None):
    if days:
        return max(1, int(days))
    try:
        v = frappe.conf.get("ec_alerts_coverage_window_days")
        return max(1, int(float(v))) if v not in (None, "") else DEFAULT_WINDOW_DAYS
    except Exception:
        return DEFAULT_WINDOW_DAYS


def missing_rows(brands=None, days=None, platform=None, limit=None):
    """Order-derived missing-coverage SKUs. ONE batched query (no N+1). Returns
    list of dicts {brand, seller_sku, product_name, rsp_price, order_lines,
    last_order}, distinct per (brand, seller_sku). `brands`: None = all brands
    (supervisor); [] = empty scope -> []. Callers enforce brand scope."""
    if brands is not None:
        brands = [b for b in brands if b]
        if not brands:
            return []
    since = str(add_days(nowdate(), -window_days(days))) + " 00:00:00"
    params = {"since": since, "today": nowdate()}
    conds = ["ol.order_datetime >= %(since)s",
             "oi.seller_sku IS NOT NULL", "oi.seller_sku != ''",
             # exclude still-UNRESOLVED rows (no own brand AND no Active mapping):
             # they stay OUT of Price Setup, handled by missing_brand_mapping.
             _RESOLVED_BRAND + " IS NOT NULL", _RESOLVED_BRAND + " != ''"]
    if brands is not None:
        conds.append(_RESOLVED_BRAND + " IN %(brands)s")
        params["brands"] = tuple(brands)
    if platform and platform != "All":
        conds.append("ol.platform = %(platform)s")
        params["platform"] = platform
    conds.append("NOT " + _COVERED)
    # RC7-C: a dedicated gift/freebie Seller SKU that is currently exempt is NOT a
    # coverage gap -> exclude it from the missing-policy count (shared matcher; date =
    # today, so it only drops out during the effective window and returns afterwards).
    conds.append("NOT " + exemption_guard.exempt_exists_sql(
        _RESOLVED_BRAND, "ol.platform", "oi.seller_sku", "%(today)s"))
    lim = "LIMIT %(limit)s" if limit else ""
    if limit:
        params["limit"] = int(limit)
    # Built by concatenation (NOT %-formatting): the placeholders %(since)s /
    # %(brands)s / %(platform)s / %(today)s / %(limit)s stay literal and are
    # bound by frappe.db.sql; the resolved-brand / shop-join fragments are
    # trusted constants (no user input).
    query = (
        "SELECT " + _RESOLVED_BRAND + " AS brand, oi.seller_sku AS seller_sku, "
        "MAX(oi.product_name) AS product_name, MAX(oi.list_price) AS rsp_price, "
        "COUNT(*) AS order_lines, MAX(ol.order_datetime) AS last_order "
        "FROM `tabEC Marketplace Order Item` oi "
        "JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name "
        + _SHOP_JOIN + " "
        "WHERE " + " AND ".join(conds) + " "
        "GROUP BY " + _RESOLVED_BRAND + ", oi.seller_sku "
        "ORDER BY order_lines DESC " + lim)
    return frappe.db.sql(query, params, as_dict=True)


def missing_counts(brands=None, days=None):
    """{brand: distinct missing seller_sku count}. Batched (one query). None =
    all brands. Rows are already distinct per (brand, seller_sku)."""
    out = {}
    for r in missing_rows(brands, days=days):
        out[r["brand"]] = out.get(r["brand"], 0) + 1
    return out


def missing_count(brand, days=None):
    """Distinct missing seller_sku count for ONE brand (Setup ToDo metric)."""
    if not brand:
        return 0
    return missing_counts([brand], days=days).get(brand, 0)


def _total_order_skus(brand, days=None, platform=None):
    # Denominator for coverage_pct: must attribute by the SAME resolved brand as
    # the numerator (missing_rows), else the percentage is inconsistent for
    # shop-mapping-resolved brands.
    since = str(add_days(nowdate(), -window_days(days))) + " 00:00:00"
    params = {"brand": brand, "since": since}
    cond = ""
    if platform and platform != "All":
        cond = " AND ol.platform = %(platform)s"
        params["platform"] = platform
    query = (
        "SELECT COUNT(DISTINCT oi.seller_sku) AS n "
        "FROM `tabEC Marketplace Order Item` oi "
        "JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name "
        + _SHOP_JOIN + " "
        "WHERE " + _RESOLVED_BRAND + " = %(brand)s AND ol.order_datetime >= %(since)s "
        "AND oi.seller_sku IS NOT NULL AND oi.seller_sku != ''" + cond)
    row = frappe.db.sql(query, params, as_dict=True)
    return int(row[0].n) if row else 0


def coverage_report(brand, days=None, platform=None, limit=200):
    """For the coverage modal: full missing_count + a (capped) missing list +
    total order SKUs + coverage_pct. missing_count is the FULL distinct count so
    it equals the chip count; `missing` is the top-`limit` display rows."""
    full = missing_rows([brand], days=days, platform=platform)
    cnt = len(full)
    missing = full[:int(limit)] if limit else full
    total = _total_order_skus(brand, days=days, platform=platform)
    return {"brand": brand, "days": window_days(days), "missing": missing,
            "missing_count": cnt, "checked": total,
            "coverage_pct": (round(100.0 * (total - cnt) / total, 1) if total else None)}
