"""Rule B - brand-scoped EC Price Policy lookup.

Brand is MANDATORY (multi-brand directive: a policy of one brand is never
applied to another). Priority levels (approved):
  1 brand + platform + shop + item
  2 brand + platform + shop + seller_sku
  3 brand + platform + item            (policy has no shop)
  4 brand + platform + seller_sku      (policy has no shop)
  5 brand + platform=All + item / seller_sku
  6 brand-level fallback, only if policy.is_brand_fallback = 1 (explicit opt-in)
Effective window: effective_from <= on_date <= effective_to, empty = open
(both ends inclusive). status must be Active.
"""
import frappe


def find_policy(brand, platform=None, shop=None, item=None, seller_sku=None, on_date=None):
    """Returns (policy_doc_or_None, priority_level_or_None)."""
    if not brand:
        return None, None
    on_date = str(on_date or frappe.utils.nowdate())

    levels = []
    if shop and item:
        levels.append((1, {"platform": platform, "shop": shop, "item": item}))
    if shop and seller_sku:
        levels.append((2, {"platform": platform, "shop": shop, "seller_sku": seller_sku}))
    if item:
        levels.append((3, {"platform": platform, "item": item, "shop": ("is", "not set")}))
    if seller_sku:
        levels.append((4, {"platform": platform, "seller_sku": seller_sku, "shop": ("is", "not set")}))
    if item:
        levels.append((5, {"platform": "All", "item": item, "shop": ("is", "not set")}))
    if seller_sku:
        levels.append((5, {"platform": "All", "seller_sku": seller_sku, "shop": ("is", "not set")}))
    levels.append((6, {"is_brand_fallback": 1, "platform": ("in", [platform, "All"]) if platform else "All"}))

    for level, extra in levels:
        if level in (1, 2, 3, 4) and not platform:
            continue
        filters = {"brand": brand, "status": "Active"}
        filters.update(extra)
        rows = frappe.get_all(
            "EC Price Policy",
            filters=filters,
            fields=["name", "effective_from", "effective_to"],
            order_by="modified desc",
            limit=20,
        )
        for r in rows:
            if _in_window(r, on_date):
                return frappe.get_doc("EC Price Policy", r.name), level
    return None, None


def _in_window(row, on_date):
    f, t = row.get("effective_from"), row.get("effective_to")
    if f and str(f) > on_date:
        return False
    if t and str(t) < on_date:
        return False
    return True
