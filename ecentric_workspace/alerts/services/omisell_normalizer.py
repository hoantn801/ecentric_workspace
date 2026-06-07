"""Omisell payload -> normalized order dict (the shape services/ingestion.py
already accepts). Pure transformation - NO network, NO writes.

Status filtering (decision Q-D2, FINALIZED 2026-06-10 as "PRICE-RISK /
CUSTOMER-CHECKOUT statuses" - not "real sales"): if a customer could place
an order at a price, the price exposure already happened, even if the order
is later cancelled (e.g. 702 Huy boi doi tac IS included). Production
allowlist lives in site_config:
  ec_alerts_omisell_allowed_status_ids = [250, 300, 400, 460, 500, 600, 702, 900]
Excluded: draft / unpaid / payment-failed / invalid / pre-creation failures.
Mechanism is CENTRALIZED here and configurable:
  * If site_config `ec_alerts_omisell_allowed_status_ids` (list of ints) is
    set, it is authoritative (use after T2/T3 confirm the real ids).
  * Otherwise a conservative keyword rule on status_name applies:
    excluded keywords win; unknown statuses are EXCLUDED and reported
    (never silently ingested) - per "do not hardcode unclear status_id".

Price mapping (decision Q-D5, PROVISIONAL until T2 golden file):
  unit_check_price = catalogue_items[].discounted_price
  seller_discount  = discount_seller + voucher_seller
  platform_discount= discount_platform + voucher_platform
  customer_paid_price left empty (Omisell transaction_amount is order-level).
"""
from datetime import datetime

import frappe

EXCLUDE_KEYWORDS = ("cancel", "return", "fail", "draft", "unpaid", "invalid", "error")
INCLUDE_KEYWORDS = ("paid", "ready to ship", "rts", "process", "ship", "deliver",
                    "complete", "done")

PLATFORM_MAP = (("shopee", "Shopee"), ("lazada", "Lazada"), ("tiktok", "TikTok"))


def is_real_sale(status_id, status_name):
    """'real sale' kept as the FUNCTION NAME for API stability; semantics are
    'price-risk / customer-checkout' per the finalized Q-D2 decision (see
    module docstring). Returns (bool, reason). Conservative: unknown -> excluded."""
    try:
        allowed = frappe.conf.get("ec_alerts_omisell_allowed_status_ids")
    except Exception:
        allowed = None
    if allowed:
        ok = status_id in allowed or str(status_id) in [str(x) for x in allowed]
        return ok, ("conf_allowlist" if ok else "conf_excluded")
    name = (status_name or "").lower()
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return False, "excluded_keyword"
    if any(k in name for k in INCLUDE_KEYWORDS):
        return True, "included_keyword"
    return False, "unknown_status"


def map_platform(value):
    v = (value or "").lower()
    for key, label in PLATFORM_MAP:
        if key in v:
            return label
    return "Other"


def epoch_to_site(ts):
    if not ts:
        return None
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return None
    try:
        from frappe.utils import convert_utc_to_system_timezone
        return convert_utc_to_system_timezone(datetime.utcfromtimestamp(ts)).replace(tzinfo=None)
    except Exception:
        return datetime.fromtimestamp(ts)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def normalize_order_detail(d):
    """d = Omisell Get Order Detail `data` object. Returns normalized order
    dict for ingestion.ingest_orders (one dict)."""
    lines = []
    for pi, parcel in enumerate(d.get("parcels") or []):
        pid = parcel.get("package_number") or ("P%d" % (pi + 1))
        for item in parcel.get("catalogue_items") or []:
            sku = item.get("catalogue_sku")
            lines.append({
                # Omisell has no explicit line id -> deterministic synthetic id
                "external_line_id": "%s:%s" % (pid, sku),
                "seller_sku": sku,
                "product_name": item.get("product_name"),
                "quantity": _f(item.get("quantity")),
                "list_price": _f(item.get("original_price")),
                # Q-D5 PROVISIONAL - confirm unit/voucher/subsidy semantics at T2
                "unit_check_price": _f(item.get("discounted_price")) or None,
                "seller_discount": _f(item.get("discount_seller")) + _f(item.get("voucher_seller")),
                "platform_discount": _f(item.get("discount_platform")) + _f(item.get("voucher_platform")),
                "customer_paid_price": None,
            })
    status_id, status_name = d.get("status_id"), d.get("status_name")
    return {
        "source_system": "Omisell",
        "external_order_id": d.get("omisell_order_number"),
        "platform": map_platform(d.get("platform_name") or d.get("platform")),
        "omisell_shop_id": str(d.get("shop_id")) if d.get("shop_id") is not None else None,
        "order_datetime": epoch_to_site(d.get("created_time")),
        "order_status": "%s - %s" % (status_id, status_name),
        "items": lines,
        # carried for filtering/reporting; ingestion ignores unknown keys
        "_status_id": status_id,
        "_status_name": status_name,
        "_platform_order_number": d.get("order_number"),
    }


def normalize_shop(s):
    return {"shop_id": str(s.get("shop_id") or s.get("id") or ""),
            "shop_name": s.get("shop_name") or s.get("name"),
            "platform": map_platform(s.get("platform_name") or s.get("platform"))}
