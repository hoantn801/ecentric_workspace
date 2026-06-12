"""G2.2 - Omisell catalogue/list -> EC Marketplace SKU Catalog sync.

Source of truth: GET /api/v2/public/catalogue/list (probe-confirmed; it is
shop-scoped: platform/shop_id/shop_name/status/external_id/images/stock/
variants). product/list is NOT used (no shop scope).

Layering:
  * PURE (frappe-free, unit-testable): normalize_catalogue(), flatten of
    variants into their own rows, platform normalization, compare_price().
  * Frappe-side: upsert_catalogue_row() - writes ONLY to EC Marketplace SKU
    Catalog (idempotent, hash-gated, key = source|omisell_shop_id|seller_sku
    via sku_catalog.catalog_key - SAME identity as order-derived rows).

PRICE GUARD (user decision 2026-06-12): catalogue.price is NOT yet trusted
as RSP. An existing ORDER-DERIVED rsp_price is never overwritten by the
catalogue price; mismatches are flagged price_confidence=low in `note`.
Extra catalogue facts (sale price, image, variant lineage, raw status,
stock) ride in `note` as compact JSON - NO schema change, NO migration.
source_level uses the EXISTING Select option 'omisell_product' (adding an
'omisell_catalogue' option would require a DocType change + migrate; the
note JSON carries src='catalogue/list').
"""
import hashlib
import json

# Platform aliases (blocker fix 2026-06-12: FES preview returned
# platform_raw='shopee_v2' -> wrongly normalized to 'Other'). Matching is
# prefix-based on the lowercased, '-'->'_' form, so shopee / shopee_v2 /
# shopee-v2 / lazada_v2 / tiktok_shop all map correctly.
PLATFORM_PREFIXES = (("shopee", "Shopee"), ("lazada", "Lazada"),
                     ("tiktok", "TikTok"))
PRICE_TOLERANCE = 0.005          # 0.5% relative tolerance for "match"
NOTE_MAX = 1200
IMAGE_URL_MAX = 300


def _s(v):
    return "" if v is None else str(v).strip()


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def norm_platform(raw):
    v = _s(raw).lower().replace("-", "_")
    for prefix, name in PLATFORM_PREFIXES:
        if v.startswith(prefix):
            return name
    return "Other"


def compare_price(catalogue_price, order_rsp, tolerance=PRICE_TOLERANCE):
    """'match' | 'mismatch' | 'no_reference'. Reference = order-derived RSP."""
    c, o = _f(catalogue_price), _f(order_rsp)
    if o is None or o == 0:
        return "no_reference"
    if c is None:
        return "mismatch"
    return "match" if abs(c - o) <= abs(o) * tolerance else "mismatch"


def _first_image(images):
    if isinstance(images, (list, tuple)) and images:
        return _s(images[0])[:IMAGE_URL_MAX]
    if isinstance(images, str):
        return _s(images)[:IMAGE_URL_MAX]
    return ""


def _base_row(c):
    return {
        "seller_sku": _s(c.get("sku")),
        "product_name": _s(c.get("name"))[:140],
        "price": _f(c.get("price")),
        "price_sale": _f(c.get("price_sale")),
        "image_url": _first_image(c.get("images")),
        "platform_raw": _s(c.get("platform")),
        "platform": norm_platform(c.get("platform")),
        "omisell_shop_id": _s(c.get("shop_id")),
        "shop_name": _s(c.get("shop_name")),
        "external_product_id": _s(c.get("external_id")),
        "catalogue_id": _s(c.get("catalogue_id") or c.get("id")),
        "status_raw": _s(c.get("status")),
        "status_name": _s(c.get("status_name")),
        "external_stock": c.get("external_stock"),
        "is_variant": 0,
        "parent_catalogue_id": "",
        "parent_sku": "",
    }


def normalize_catalogue(c):
    """One raw catalogue item -> flat rows: parent (when it has a sellable
    sku) + one row per variant (variant.sku = seller_sku; inherits parent
    fields where the variant does not carry its own). PURE."""
    parent = _base_row(c or {})
    rows = []
    if parent["seller_sku"]:
        rows.append(parent)
    for v in (c or {}).get("variants") or []:
        if not isinstance(v, dict):
            continue
        row = dict(parent)
        row["seller_sku"] = _s(v.get("sku"))
        if not row["seller_sku"]:
            continue
        if _s(v.get("name")):
            row["product_name"] = _s(v.get("name"))[:140]
        if _f(v.get("price")) is not None:
            row["price"] = _f(v.get("price"))
        if _f(v.get("price_sale")) is not None:
            row["price_sale"] = _f(v.get("price_sale"))
        img = _first_image(v.get("images"))
        if img:
            row["image_url"] = img
        if _s(v.get("external_id")):
            row["external_product_id"] = _s(v.get("external_id"))
        if v.get("external_stock") is not None:
            row["external_stock"] = v.get("external_stock")
        row["is_variant"] = 1
        row["parent_catalogue_id"] = parent["catalogue_id"]
        row["parent_sku"] = parent["seller_sku"]
        rows.append(row)
    return rows


def build_note(row, price_confidence):
    """Compact JSON for the existing Small Text `note` field (no migration)."""
    payload = {"src": "catalogue/list",
               "price_confidence": price_confidence,
               "sale_price": row.get("price_sale"),
               "catalogue_price": row.get("price"),
               "image_url": row.get("image_url") or None,
               "catalogue_id": row.get("catalogue_id") or None,
               "shop_name": row.get("shop_name") or None,
               "platform_raw": row.get("platform_raw") or None,
               "status_raw": row.get("status_raw") or None,
               "status_name": row.get("status_name") or None,
               "external_stock": row.get("external_stock"),
               "is_variant": row.get("is_variant") or 0,
               "parent_sku": row.get("parent_sku") or None,
               "parent_catalogue_id": row.get("parent_catalogue_id") or None}
    return json.dumps({k: v for k, v in payload.items() if v is not None},
                      ensure_ascii=True)[:NOTE_MAX]


def row_hash(row):
    raw = "|".join(_s(row.get(k)) for k in (
        "seller_sku", "product_name", "price", "price_sale", "image_url",
        "platform", "omisell_shop_id", "external_product_id", "catalogue_id",
        "status_raw", "status_name", "external_stock", "is_variant",
        "parent_sku"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


# --------------------------- frappe side ------------------------------------

def upsert_catalogue_row(brand, row):
    """Idempotent upsert of one normalized catalogue row. Writes ONLY to
    EC Marketplace SKU Catalog. Returns
    'created'|'enriched'|'unchanged'|'skipped'.

    PRICE GUARD: if the existing row is order_derived with an RSP, the
    catalogue NEVER overwrites rsp_price (order-derived wins until the user
    explicitly confirms otherwise); the catalogue price + confidence verdict
    are recorded in note JSON instead."""
    import frappe
    from frappe.utils import now_datetime
    from ecentric_workspace.alerts.services import sku_catalog

    sku = row.get("seller_sku")
    if not sku:
        return "skipped"
    key = sku_catalog.catalog_key("Omisell", row.get("omisell_shop_id"), sku)
    existing = frappe.db.get_value(
        "EC Marketplace SKU Catalog", {"catalog_key": key},
        ["name", "rsp_price", "source_level", "raw_payload_hash"], as_dict=True)
    if existing and existing.source_level == "order_derived" and existing.rsp_price:
        verdict = compare_price(row.get("price"), existing.rsp_price)
        confidence = "high" if verdict == "match" else "low"
    else:
        confidence = "unverified"
    note = build_note(row, confidence)
    h = row_hash(row) + "|" + confidence[:1]
    now = now_datetime()
    shop = frappe.db.get_value("EC Marketplace Shop",
                               {"omisell_shop_id": row.get("omisell_shop_id")},
                               "name") if row.get("omisell_shop_id") else None
    if existing:
        if existing.raw_payload_hash == h:
            frappe.db.set_value("EC Marketplace SKU Catalog", existing.name,
                                {"last_seen_at": now, "is_active": 1},
                                update_modified=False)
            return "unchanged"
        doc = frappe.get_doc("EC Marketplace SKU Catalog", existing.name)
        if row.get("product_name"):
            doc.product_name = row["product_name"]
        if row.get("external_product_id"):
            doc.external_product_id = row["external_product_id"]
        doc.platform = doc.platform or row.get("platform")
        doc.shop = doc.shop or shop
        # PRICE GUARD: only a NON-order-derived row may take catalogue price.
        if not (existing.source_level == "order_derived" and existing.rsp_price):
            if row.get("price") is not None:
                doc.rsp_price = row["price"]
        doc.note = note
        doc.last_seen_at = now
        doc.is_active = 1
        doc.status = "Active"
        doc.raw_payload_hash = h
        doc.save(ignore_permissions=True)
        return "enriched"
    frappe.get_doc({
        "doctype": "EC Marketplace SKU Catalog",
        "catalog_key": key, "brand": brand or None,
        "platform": row.get("platform"), "shop": shop,
        "omisell_shop_id": row.get("omisell_shop_id") or None,
        "seller_sku": sku, "product_name": row.get("product_name"),
        "rsp_price": row.get("price"),
        "external_product_id": row.get("external_product_id") or None,
        "source_system": "Omisell", "source_level": "omisell_product",
        "note": note, "first_seen_at": now, "last_seen_at": now,
        "is_active": 1, "status": "Active", "raw_payload_hash": h,
    }).insert(ignore_permissions=True)
    return "created"
