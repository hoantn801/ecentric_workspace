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

Brand scope / permission are enforced by the API callers (this service takes a
brand list and trusts it).
"""
import frappe
from frappe.utils import add_days, nowdate

DEFAULT_WINDOW_DAYS = 30

# Mirrors policy_lookup.find_policy EXISTENCE for a line (brand=ol.brand):
#   L1-L4  specific platform, shop-specific OR no-shop, item OR seller_sku
#   L5     platform 'All', no shop, item OR seller_sku
#   L6     is_brand_fallback, platform in (line.platform, 'All')
# An order line's platform is always set, so the find_policy "platform required
# for L1-L4" guard is implicitly satisfied.
_COVERED = (
    "EXISTS (SELECT 1 FROM `tabEC Price Policy` pp "
    "WHERE pp.brand = ol.brand AND pp.status = 'Active' "
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
             "oi.seller_sku IS NOT NULL", "oi.seller_sku != ''"]
    if brands is not None:
        conds.append("ol.brand IN %(brands)s")
        params["brands"] = tuple(brands)
    if platform and platform != "All":
        conds.append("ol.platform = %(platform)s")
        params["platform"] = platform
    conds.append("NOT " + _COVERED)
    lim = ""
    if limit:
        params["limit"] = int(limit)
        lim = "LIMIT %(limit)s"
    return frappe.db.sql(
        """SELECT ol.brand AS brand, oi.seller_sku AS seller_sku,
                  MAX(oi.product_name) AS product_name, MAX(oi.list_price) AS rsp_price,
                  COUNT(*) AS order_lines, MAX(ol.order_datetime) AS last_order
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE %s
           GROUP BY ol.brand, oi.seller_sku
           ORDER BY order_lines DESC %s""" % (" AND ".join(conds), lim),
        params, as_dict=True)


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
    since = str(add_days(nowdate(), -window_days(days))) + " 00:00:00"
    params = {"brand": brand, "since": since}
    cond = ""
    if platform and platform != "All":
        cond = "AND ol.platform = %(platform)s "
        params["platform"] = platform
    row = frappe.db.sql(
        """SELECT COUNT(DISTINCT oi.seller_sku) AS n
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE ol.brand = %%(brand)s AND ol.order_datetime >= %%(since)s
             AND oi.seller_sku IS NOT NULL AND oi.seller_sku != '' %s""" % cond,
        params, as_dict=True)
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
