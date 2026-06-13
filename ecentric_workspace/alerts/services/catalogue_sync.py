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


# --- confirm/preview param resolution (PURE; hotfix 2026-06-12) -------------
# Bad Gateway root cause: confirm defaulted to 40 pages and silently IGNORED
# caller cap params sent under alias names (pages_requested / row_cap /
# limit) - a heavy synchronous run blew the gunicorn timeout. All alias
# resolution + clamping is pure and unit-tested here.
CONFIRM_DEFAULT_PAGES = 2
CONFIRM_DEFAULT_ROWS = 300
CONFIRM_MAX_PAGES_SYNC = 5      # hard sync cap unless allow_heavy=1 (SM)
CONFIRM_MAX_PAGES_HEAVY = 40
CONFIRM_MAX_ROWS = 5000
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100
TRUTHY = ("1", "true", "yes", "on")


def _first(*vals):
    for v in vals:
        if v not in (None, ""):
            return v
    return None


def _toint(v, default):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def resolve_confirm_params(pages=None, max_pages=None, pages_requested=None,
                           page_size=None, max_rows=None, row_cap=None,
                           limit=None, start_page=None, allow_heavy=0):
    """Honor ALL caller aliases, clamp to sync-safe bounds, echo effective
    values. pages aliases: pages|max_pages|pages_requested (default 2,
    hard <=5 unless allow_heavy). rows aliases: max_rows|row_cap|limit
    (default 300, hard <=5000)."""
    heavy = str(allow_heavy).strip().lower() in TRUTHY
    req_pages = _toint(_first(pages, max_pages, pages_requested),
                       CONFIRM_DEFAULT_PAGES)
    pages_cap = CONFIRM_MAX_PAGES_HEAVY if heavy else CONFIRM_MAX_PAGES_SYNC
    return {
        "effective_pages_requested": max(1, min(req_pages, pages_cap)),
        "effective_page_size": max(1, min(_toint(page_size, PAGE_SIZE_DEFAULT),
                                          PAGE_SIZE_MAX)),
        "effective_row_cap": max(1, min(_toint(_first(max_rows, row_cap, limit),
                                               CONFIRM_DEFAULT_ROWS),
                                        CONFIRM_MAX_ROWS)),
        "start_page": max(1, _toint(start_page, 1)),
        "allow_heavy": heavy,
    }


def row_hash(row):
    raw = "|".join(_s(row.get(k)) for k in (
        "seller_sku", "product_name", "price", "price_sale", "image_url",
        "platform", "omisell_shop_id", "external_product_id", "catalogue_id",
        "status_raw", "status_name", "external_stock", "is_variant",
        "parent_sku"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


# Phase 3 (2026-06-13): promoted catalogue metadata fields (real columns).
# All are catalogue-sourced and overwrite-latest EXCEPT rsp_price (untouched -
# order-derived priority). The original `note` JSON is kept unchanged.
PROMOTED_FIELDS = ("image_url", "catalogue_price", "sale_price",
                   "external_stock", "product_status", "catalogue_id",
                   "parent_sku", "is_variant", "price_confidence",
                   "last_catalogue_sync_at")


def _int_or_none(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def promoted_values(row, confidence, now):
    """Map a normalized catalogue row -> the 10 promoted DocType fields.
    PURE (no frappe). rsp_price is intentionally NOT here."""
    return {
        "image_url": (row.get("image_url") or None),
        "catalogue_price": row.get("price"),
        "sale_price": row.get("price_sale"),
        "external_stock": _int_or_none(row.get("external_stock")),
        "product_status": (row.get("status_name") or row.get("status_raw") or None),
        "catalogue_id": (row.get("catalogue_id") or None),
        "parent_sku": (row.get("parent_sku") or None),
        "is_variant": 1 if row.get("is_variant") else 0,
        "price_confidence": confidence,
        "last_catalogue_sync_at": now,
    }


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
        doc.note = note                 # original JSON kept (compat/audit)
        for k, v in promoted_values(row, confidence, now).items():
            setattr(doc, k, v)          # promoted fields overwrite-latest
        doc.last_seen_at = now
        doc.is_active = 1
        doc.status = "Active"
        doc.raw_payload_hash = h
        doc.save(ignore_permissions=True)  # rsp_price NOT touched above
        return "enriched"
    new_doc = {
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
    }
    new_doc.update(promoted_values(row, confidence, now))
    frappe.get_doc(new_doc).insert(ignore_permissions=True)
    return "created"
