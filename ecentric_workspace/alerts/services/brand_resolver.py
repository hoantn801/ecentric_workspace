"""Brand / shop / owner resolution. Brand source of truth = Brand Approver;
shop->brand mapping = EC Marketplace Shop (decision in 00_PRECODE_REPORT s17).

Brand resolution priority (approved):
  1. omisell_shop_id -> EC Marketplace Shop (Active) -> shop.brand
  2. payload brand field, ONLY if it names an existing Active Brand Approver
  3. (SKU-based: intentionally absent - no SKU->brand source of truth exists)
  4. unresolved -> caller raises missing_brand_mapping alert path
"""
import frappe


def resolve_shop(omisell_shop_id):
    """Return EC Marketplace Shop name or None (Active shops only)."""
    if not omisell_shop_id:
        return None
    return frappe.db.get_value(
        "EC Marketplace Shop",
        {"omisell_shop_id": str(omisell_shop_id).strip(), "status": "Active"},
        "name",
    )


def resolve_brand(omisell_shop_id=None, payload_brand=None):
    """Returns (brand_or_None, shop_name_or_None)."""
    shop = resolve_shop(omisell_shop_id)
    if shop:
        brand = frappe.db.get_value("EC Marketplace Shop", shop, "brand")
        if brand:
            return brand, shop
    if payload_brand and frappe.db.exists(
        "Brand Approver", {"name": payload_brand, "status": "Active"}
    ):
        return payload_brand, shop
    return None, shop


def resolve_owner(shop_name, brand):
    """Owner resolution per decision D1:
    shop.kam_owner -> brand.kam_owner -> brand.manager_email ->
    brand.leader_email -> None (alert stays unowned, visible to supervisors)."""
    if shop_name:
        kam = frappe.db.get_value("EC Marketplace Shop", shop_name, "kam_owner")
        if kam:
            return kam
    if brand:
        row = frappe.db.get_value(
            "Brand Approver", brand,
            ["kam_owner", "manager_email", "leader_email"], as_dict=True,
        )
        if row:
            return row.kam_owner or row.manager_email or row.leader_email
    return None
