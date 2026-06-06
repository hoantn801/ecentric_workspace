"""Rule C - baseline price + confidence.

Priority (approved):
  1. 30-day historical MEDIAN unit_check_price from EC Marketplace Order Item,
     same brand (+ platform/shop when known), same item or seller_sku,
     EXCLUDING the order being checked (self-influence / re-sync guard).
     n >= 5  -> confidence High
  2. EC Price Policy.reference_price -> Medium
  3. EC Price Policy.min_price       -> Low (alert only - never lock)
Only High/Medium may produce a Stock Safety Lock action (enforced in
action_queue, not here).
"""
import statistics

import frappe
from frappe.utils import add_days, now_datetime

HISTORY_DAYS = 30
HIGH_MIN_COUNT = 5


def get_baseline(brand, platform=None, shop=None, item=None, seller_sku=None,
                 policy=None, exclude_order_log=None):
    """Returns (baseline_price, confidence, source) - all None when nothing found."""
    prices = _history_prices(brand, platform, shop, item, seller_sku, exclude_order_log)
    if len(prices) >= HIGH_MIN_COUNT:
        return float(statistics.median(prices)), "High", "30d_median(n=%d)" % len(prices)
    pol = policy or {}
    ref = pol.get("reference_price")
    if ref:
        return float(ref), "Medium", "reference_price"
    mn = pol.get("min_price")
    if mn:
        return float(mn), "Low", "min_price"
    return None, None, None


def _history_prices(brand, platform, shop, item, seller_sku, exclude_order_log):
    if not brand or not (item or seller_sku):
        return []
    conds = ["l.brand = %(brand)s", "l.order_datetime >= %(cutoff)s",
             "i.unit_check_price > 0"]
    params = {
        "brand": brand,
        "cutoff": add_days(now_datetime(), -HISTORY_DAYS),
        "item": item, "sku": seller_sku, "platform": platform,
        "shop": shop, "exclude": exclude_order_log,
    }
    if platform:
        conds.append("l.platform = %(platform)s")
    if shop:
        conds.append("l.shop = %(shop)s")
    if exclude_order_log:
        conds.append("l.name != %(exclude)s")
    if item and seller_sku:
        conds.append("(i.item = %(item)s OR i.seller_sku = %(sku)s)")
    elif item:
        conds.append("i.item = %(item)s")
    else:
        conds.append("i.seller_sku = %(sku)s")
    rows = frappe.db.sql(
        """SELECT i.unit_check_price
           FROM `tabEC Marketplace Order Item` i
           JOIN `tabEC Marketplace Order Log` l ON i.parent = l.name
           WHERE %s""" % " AND ".join(conds),
        params,
    )
    return [float(r[0]) for r in rows if r and r[0]]
