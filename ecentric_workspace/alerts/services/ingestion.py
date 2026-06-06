"""Mock/normalized order ingestion -> EC Marketplace Order Log (+items) ->
rules engine. IDEMPOTENT: order_key (source|external_order_id) is unique;
re-ingesting the same payload updates nothing and re-runs checks, which the
dedupe keys turn into no-ops (test 10).

Normalized payload schema (one order):
{
  "source_system": "Omisell" (default),
  "external_order_id": "ORD-1",            # required
  "platform": "Shopee|Lazada|TikTok|Other",
  "omisell_shop_id": "12345",              # -> EC Marketplace Shop mapping
  "brand": "BBT-VN",                       # optional fallback, must match Brand Approver
  "order_datetime": "2026-06-07 10:00:00",
  "order_status": "PAID",
  "items": [{
      "external_line_id": "L1",            # required per line
      "item": "ITEM-0001",                 # optional ERPNext Item code
      "seller_sku": "SKU-A",
      "external_product_id": "9988",       # optional, used in C1 dedupe keys
      "product_name": "...",
      "quantity": 1,
      "list_price": 99000, "seller_discount": 0, "platform_discount": 0,
      "customer_paid_price": 99000          # LINE total
  }]
}
NO HTTP here - Phase D will add the real Omisell pull behind the same
normalizer. This module only accepts already-normalized dicts.
"""
import hashlib
import json

import frappe
from frappe.utils import now_datetime

from . import alert_engine, brand_resolver

LINE_FIELDS = ("external_line_id", "seller_sku", "product_name", "quantity",
               "list_price", "seller_discount", "platform_discount",
               "customer_paid_price")


def ingest_orders(orders, run_checks=True):
    """orders: list of normalized order dicts. Returns per-order results.
    One bad order never kills the batch."""
    results = []
    for o in orders:
        try:
            results.append(_ingest_one(o or {}, run_checks))
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "alerts.ingestion %s" % (o or {}).get("external_order_id"))
            results.append({"external_order_id": (o or {}).get("external_order_id"),
                            "status": "failed"})
    return results


def _ingest_one(o, run_checks):
    eid = str(o.get("external_order_id") or "").strip()
    if not eid:
        frappe.throw("external_order_id is required")
    src = o.get("source_system") or "Omisell"
    payload_hash = hashlib.sha256(
        json.dumps(o, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    existing = frappe.db.get_value(
        "EC Marketplace Order Log", {"order_key": "%s|%s" % (src, eid)},
        ["name", "raw_payload_hash"], as_dict=True)

    if existing and existing.raw_payload_hash == payload_hash:
        # unchanged re-sync: re-run checks; dedupe guarantees no duplicates
        summary = alert_engine.check_order_log(
            existing.name, raw_shop_id=o.get("omisell_shop_id")) if run_checks else None
        return {"order": existing.name, "status": "unchanged", "summary": summary}

    brand, shop = brand_resolver.resolve_brand(o.get("omisell_shop_id"), o.get("brand"))

    if existing:
        doc = frappe.get_doc("EC Marketplace Order Log", existing.name)
        doc.items = []
        status = "updated"
    else:
        doc = frappe.new_doc("EC Marketplace Order Log")
        status = "created"

    doc.update({
        "source_system": src,
        "external_order_id": eid,
        "platform": o.get("platform") or "Other",
        "shop": shop,
        "brand": brand,
        "order_datetime": o.get("order_datetime") or now_datetime(),
        "order_status": o.get("order_status"),
        "raw_payload_hash": payload_hash,
        "sync_status": "Pending",
        "sync_error": None,
    })
    for ln in o.get("items") or []:
        row = {k: ln.get(k) for k in LINE_FIELDS}
        item_code = ln.get("item") or ln.get("sku")
        if item_code and frappe.db.exists("Item", item_code):
            row["item"] = item_code
        doc.append("items", row)
    doc.save(ignore_permissions=True)

    summary = None
    if run_checks:
        try:
            summary = alert_engine.check_order_log(
                doc.name, raw_shop_id=o.get("omisell_shop_id"))
        except Exception:
            doc.db_set("sync_status", "Failed", update_modified=False)
            doc.db_set("sync_error", frappe.get_traceback()[-500:], update_modified=False)
            frappe.log_error(frappe.get_traceback(), "alerts.check %s" % doc.name)
            return {"order": doc.name, "status": "check_failed"}
    return {"order": doc.name, "status": status, "summary": summary}
