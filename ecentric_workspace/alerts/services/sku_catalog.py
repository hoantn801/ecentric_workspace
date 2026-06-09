"""Phase G2.1 - order-derived marketplace SKU catalog.

Upserts EC Marketplace SKU Catalog rows from ingested order lines (NO Omisell
call - all data already in Frappe). Upsert identity:
    catalog_key = source_system | omisell_shop_id | seller_sku
RSP = the LATEST list_price (Omisell original_price) seen for that SKU.
Idempotent: raw_payload_hash skips no-op writes; re-running never duplicates.
"""
import hashlib

import frappe
from frappe.utils import add_days, now_datetime, nowdate

MAX_LEN = 140


def catalog_key(source_system, omisell_shop_id, seller_sku):
    return _fit("%s|%s|%s" % (_s(source_system), _s(omisell_shop_id), _s(seller_sku)))


def _row_hash(product_name, rsp, platform, shop):
    raw = "|".join(_s(x) for x in (product_name, rsp, platform, shop))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


def upsert(brand, platform, shop, omisell_shop_id, seller_sku, product_name, rsp,
           source_system="Omisell", source_level="order_derived"):
    """Idempotent upsert by catalog_key. Returns 'created'|'updated'|
    'unchanged'|'skipped'."""
    sku = _s(seller_sku)
    if not sku:
        return "skipped"
    key = catalog_key(source_system, omisell_shop_id, sku)
    h = _row_hash(product_name, rsp, platform, shop)
    now = now_datetime()
    existing = frappe.db.get_value(
        "EC Marketplace SKU Catalog", {"catalog_key": key},
        ["name", "raw_payload_hash"], as_dict=True)
    if existing:
        if existing.raw_payload_hash == h:
            frappe.db.set_value("EC Marketplace SKU Catalog", existing.name,
                                {"last_seen_at": now, "is_active": 1},
                                update_modified=False)
            return "unchanged"
        doc = frappe.get_doc("EC Marketplace SKU Catalog", existing.name)
        doc.brand = brand or doc.brand
        doc.platform = platform or doc.platform
        doc.shop = shop or doc.shop
        doc.omisell_shop_id = _s(omisell_shop_id) or doc.omisell_shop_id
        if product_name:
            doc.product_name = product_name
        if rsp is not None:
            doc.rsp_price = rsp          # latest RSP wins (G2.1 decision)
        doc.last_seen_at = now
        doc.is_active = 1
        doc.status = "Active"
        doc.raw_payload_hash = h
        doc.save(ignore_permissions=True)
        return "updated"
    frappe.get_doc({
        "doctype": "EC Marketplace SKU Catalog",
        "catalog_key": key, "brand": brand or None, "platform": platform,
        "shop": shop, "omisell_shop_id": _s(omisell_shop_id) or None,
        "seller_sku": sku, "product_name": product_name, "rsp_price": rsp,
        "source_system": source_system or "Omisell", "source_level": source_level,
        "first_seen_at": now, "last_seen_at": now, "is_active": 1,
        "status": "Active", "raw_payload_hash": h,
    }).insert(ignore_permissions=True)
    return "created"


def upsert_from_order_line(log, line):
    """Inline hook from alert_engine. FAIL-OPEN: the caller wraps this in
    try/except so a catalog hiccup never breaks ingestion/pull."""
    return upsert(
        brand=log.brand, platform=log.platform, shop=log.shop,
        omisell_shop_id=log.omisell_shop_id, seller_sku=line.seller_sku,
        product_name=line.product_name, rsp=line.list_price,
        source_system=log.source_system or "Omisell")


def backfill(brand=None, days=90, limit=5000):
    """Manual rebuild from existing Order Items (joined to Order Log). Bounded;
    processes oldest->newest so the LATEST order's RSP wins. Reads orders +
    writes catalog only - NO Omisell. Returns counts."""
    conds = ["ol.order_datetime >= %s"]
    params = [str(add_days(nowdate(), -int(days))) + " 00:00:00"]
    if brand:
        conds.append("ol.brand = %s")
        params.append(brand)
    params.append(int(limit))
    rows = frappe.db.sql(
        """SELECT ol.brand, ol.platform, ol.shop, ol.omisell_shop_id,
                  ol.source_system, oi.seller_sku, oi.product_name, oi.list_price
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE %s AND oi.seller_sku IS NOT NULL AND oi.seller_sku != ''
           ORDER BY ol.order_datetime ASC LIMIT %%s""" % " AND ".join(conds),
        params, as_dict=True)
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "rows": len(rows)}
    for r in rows:
        try:
            st = upsert(r.brand, r.platform, r.shop, r.omisell_shop_id,
                        r.seller_sku, r.product_name, r.list_price,
                        source_system=r.source_system or "Omisell")
            counts[st] = counts.get(st, 0) + 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "alerts.sku_catalog.backfill")
            counts["skipped"] += 1
    return counts


def _s(v):
    return "" if v is None else str(v).strip()


def _fit(key):
    if len(key) <= MAX_LEN:
        return key
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]
    return key[: MAX_LEN - 33] + "#" + digest
