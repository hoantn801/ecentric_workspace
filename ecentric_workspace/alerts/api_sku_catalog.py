"""Phase G2.1 - SKU catalog read/search + order-derived backfill (KAM-facing).
Every endpoint: require_alert_center_access; brand-scoped via get_allowed_brands;
NO Omisell call (order-derived only); NO secret leakage; writes are Frappe-only.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, nowdate

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import sku_catalog

CAT_FIELDS = ["name", "brand", "platform", "shop", "omisell_shop_id",
              "seller_sku", "product_name", "rsp_price", "external_product_id",
              "erpnext_item_code", "source_level", "is_active", "status",
              "first_seen_at", "last_seen_at"]
MAX_PAGE = 100


@frappe.whitelist()
def list_sku_catalog(filters=None, start=0, page_len=50):
    allowed = perms.require_alert_center_access()
    f = json.loads(filters) if isinstance(filters, str) else (filters or {})
    flt = []
    for k in ("platform", "shop", "status"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    if f.get("seller_sku"):
        flt.append(["seller_sku", "like", "%%%s%%" % f["seller_sku"]])
    if f.get("is_active") in (1, "1", True, "true"):
        flt.append(["is_active", "=", 1])
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            flt.append(["brand", "=", f["brand"]])
    else:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return {"rows": [], "total": 0}
        flt.append(["brand", "in", scope])
    rows = frappe.get_all("EC Marketplace SKU Catalog", filters=flt, fields=CAT_FIELDS,
                          order_by="last_seen_at desc", start=cint(start),
                          page_length=min(cint(page_len) or 50, MAX_PAGE))
    return {"rows": rows, "total": frappe.db.count("EC Marketplace SKU Catalog", filters=flt)}


@frappe.whitelist()
def search_skus(brand, platform=None, shop=None, keyword="", limit=20):
    """Powers the policy-drawer SKU autofill. Brand-scoped. Matches seller_sku
    OR product_name."""
    perms.require_brand_access(frappe.session.user, brand)
    flt = [["brand", "=", brand], ["is_active", "=", 1]]
    if platform and platform != "All":
        flt.append(["platform", "=", platform])
    if shop:
        flt.append(["shop", "=", shop])
    kw = (keyword or "").strip()
    or_filters = None
    if kw:
        or_filters = [["seller_sku", "like", "%%%s%%" % kw],
                      ["product_name", "like", "%%%s%%" % kw]]
    rows = frappe.get_all(
        "EC Marketplace SKU Catalog", filters=flt, or_filters=or_filters,
        fields=["seller_sku", "product_name", "rsp_price", "platform", "shop",
                "omisell_shop_id", "source_level"],
        order_by="last_seen_at desc", page_length=min(cint(limit) or 20, 50))
    return {"rows": rows}


@frappe.whitelist()
def sync_sku_catalog_preview(brand, days=90):
    """Order-derived preview: how many distinct SKUs the backfill would touch
    vs what is already cataloged. Read-only."""
    perms.require_brand_access(frappe.session.user, brand)
    since = str(add_days(nowdate(), -int(days))) + " 00:00:00"
    row = frappe.db.sql(
        """SELECT COUNT(DISTINCT oi.seller_sku) AS n
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE ol.brand = %s AND ol.order_datetime >= %s
             AND oi.seller_sku IS NOT NULL AND oi.seller_sku != ''""",
        (brand, since), as_dict=True)
    existing = frappe.db.count("EC Marketplace SKU Catalog", {"brand": brand})
    return {"brand": brand, "days": int(days),
            "distinct_order_skus": (row[0].n if row else 0),
            "existing_catalog": existing}


@frappe.whitelist(methods=["POST"])
def sync_sku_catalog_confirm(brand, days=90, limit=5000):
    """Order-derived backfill (writes catalog rows from existing orders; NO
    Omisell call). Manager-level."""
    perms.require_brand_access(frappe.session.user, brand)
    if not perms.can_manage_policy(frappe.session.user, brand):
        frappe.throw(_("You cannot rebuild the catalog for brand {0}.").format(brand),
                     frappe.PermissionError)
    return sku_catalog.backfill(brand=brand, days=int(days), limit=int(limit))


@frappe.whitelist()
def policy_missing_skus(brand, platform=None, days=30, limit=200):
    """SKUs seen in recent orders with NO Active EC Price Policy. Feeds the
    coverage panel. Read-only, brand-scoped."""
    perms.require_brand_access(frappe.session.user, brand)
    since = str(add_days(nowdate(), -int(days))) + " 00:00:00"
    conds = ["ol.brand = %s", "ol.order_datetime >= %s",
             "oi.seller_sku IS NOT NULL", "oi.seller_sku != ''"]
    params = [brand, since]
    if platform and platform != "All":
        conds.append("ol.platform = %s")
        params.append(platform)
    params.append(int(limit))
    rows = frappe.db.sql(
        """SELECT oi.seller_sku, MAX(oi.product_name) AS product_name,
                  MAX(oi.list_price) AS rsp_price, COUNT(*) AS order_lines,
                  MAX(ol.order_datetime) AS last_order
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE %s GROUP BY oi.seller_sku
           ORDER BY order_lines DESC LIMIT %%s""" % " AND ".join(conds),
        params, as_dict=True)
    skus = [r.seller_sku for r in rows]
    covered = set()
    if skus:
        cov = frappe.get_all("EC Price Policy",
                             filters={"brand": brand, "status": "Active",
                                      "seller_sku": ("in", skus)},
                             fields=["seller_sku"], limit_page_length=0)
        covered = set(c.seller_sku for c in cov)
    missing = [r for r in rows if r.seller_sku not in covered]
    return {"brand": brand, "days": int(days), "missing": missing,
            "missing_count": len(missing), "checked": len(rows),
            "coverage_pct": (round(100.0 * (len(rows) - len(missing)) / len(rows), 1)
                             if rows else None)}
