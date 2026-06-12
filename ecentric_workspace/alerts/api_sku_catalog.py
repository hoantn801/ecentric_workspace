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


def resolve_search_query(q=None, query=None, search=None, keyword=None):
    """PURE: first non-empty of the supported query aliases, stripped.
    Fix 2026-06-12: callers sent `q=` which the old signature silently
    ignored -> the endpoint returned unrelated top-N brand rows."""
    for v in (q, query, search, keyword):
        if v not in (None, ""):
            s = str(v).strip()
            if s:
                return s
    return ""


def rank_sku_match(q, seller_sku, product_name):
    """PURE ranking (case-insensitive, LITERAL containment - no SQL
    wildcards): 0 = exact seller_sku, 1 = seller_sku contains q,
    2 = product_name contains q, 3 = no match (row must be dropped)."""
    ql = (q or "").strip().lower()
    if not ql:
        return 3
    sku = (seller_sku or "").strip().lower()
    if sku == ql:
        return 0
    if ql in sku:
        return 1
    if ql in (product_name or "").strip().lower():
        return 2
    return 3


@frappe.whitelist()
def search_skus(brand, platform=None, shop=None, keyword="", limit=20,
                q=None, query=None, search=None):
    """Powers the policy-drawer SKU autofill. Brand-scoped. Matches seller_sku
    OR product_name.

    Fix 2026-06-12 (LOF GBS_LOF_8936025777042-48 incident): honors
    q/query/search/keyword aliases; exact seller_sku ranks first, then
    partial-SKU, then product-name; literal-containment re-check drops SQL
    LIKE wildcard false hits (q often contains '_'); no match -> empty rows,
    never unrelated brand rows."""
    perms.require_brand_access(frappe.session.user, brand)
    flt = [["brand", "=", brand], ["is_active", "=", 1]]
    if platform and platform != "All":
        flt.append(["platform", "=", platform])
    if shop:
        flt.append(["shop", "=", shop])
    kw = resolve_search_query(q, query, search, keyword)
    or_filters = None
    lim = min(cint(limit) or 20, 50)
    fetch_len = lim
    if kw:
        like = "%" + kw + "%"
        or_filters = [["seller_sku", "like", like],
                      ["product_name", "like", like]]
        fetch_len = min(lim * 3, 150)  # headroom so ranking can promote
    rows = frappe.get_all(
        "EC Marketplace SKU Catalog", filters=flt, or_filters=or_filters,
        fields=["seller_sku", "product_name", "rsp_price", "platform", "shop",
                "omisell_shop_id", "source_level"],
        order_by="last_seen_at desc", page_length=fetch_len)
    if kw:
        ranked = [(rank_sku_match(kw, r.get("seller_sku"), r.get("product_name")), i, r)
                  for i, r in enumerate(rows)]
        rows = [r for rank, _i, r in sorted(
            (t for t in ranked if t[0] < 3), key=lambda t: (t[0], t[1]))][:lim]
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
