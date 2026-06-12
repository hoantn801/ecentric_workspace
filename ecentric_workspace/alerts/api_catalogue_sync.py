"""G2.2 - catalogue/list -> SKU Catalog: preview + confirm endpoints.

Both SM-only POST (they hit the live Omisell API, same trust level as
api_omisell). GET-only against Omisell via the frozen client chokepoint.

  * preview_catalogue_sku_sync: fetch + normalize + PRICE REPORT. Writes
    NOTHING (no DB write of any kind in this module).
  * confirm_catalogue_sku_sync: same fetch, then idempotent upserts that
    write ONLY to EC Marketplace SKU Catalog (services.catalogue_sync;
    order-derived RSP always wins - see price guard there).

Caps: pages <= MAX_PAGES_HARD, rows <= MAX_ROWS_HARD, soft time budget so a
web request can never approach the gunicorn timeout. The client already
paces ~1s/call and honors the rate-limit header; we surface the header in
the response. Re-running confirm is safe (hash-gated upsert, no dups).

NOT here by design: no scheduler, no pull/ingest/worker change, no Omisell
write, no stock write, no migration.
"""
import time

import frappe
from frappe import _

from ecentric_workspace.alerts.api_omisell import _get_bis
from ecentric_workspace.alerts.services import catalogue_sync as cs
from ecentric_workspace.alerts.services import sku_catalog
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellClient, OmisellError)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_PAGES = 2            # preview default: light touch
MAX_PAGES_HARD = 40
DEFAULT_MAX_ROWS = 1000      # confirm default cap
MAX_ROWS_HARD = 5000
TIME_BUDGET_SECONDS = 200    # stay far below gunicorn worker timeout
PRICE_REPORT_CAP = 200


def _fetch_rows(client, pages, page_size, deadline, out):
    """Paged catalogue fetch -> normalized flat rows. Read-only."""
    rows, page = [], 1
    while page <= pages:
        if time.monotonic() > deadline:
            out["timeboxed"] = "during_fetch"
            break
        payload = client.get_catalogues(page=page, page_size=page_size)
        data = (payload or {}).get("data") or {}
        results = data.get("results") or []
        if out.get("catalogues_total") is None:
            out["catalogues_total"] = data.get("count")
        out["pages_fetched"] = page
        for c in results:
            rows.extend(cs.normalize_catalogue(c))
        if not data.get("next") or not results:
            break
        page += 1
    out["rate_limit_header"] = client.last_rate_header
    return rows


def _existing_lookup(rows):
    """Read-only map catalog_key -> {name, rsp_price, source_level} for the
    fetched rows (chunked IN query)."""
    keys = list({sku_catalog.catalog_key("Omisell", r["omisell_shop_id"],
                                         r["seller_sku"]) for r in rows})
    found = {}
    for i in range(0, len(keys), 200):
        for d in frappe.get_all("EC Marketplace SKU Catalog",
                                filters={"catalog_key": ["in", keys[i:i + 200]]},
                                fields=["name", "catalog_key", "rsp_price",
                                        "source_level"]):
            found[d.catalog_key] = d
    return found


def _stats(rows, existing):
    parents = sum(1 for r in rows if not r["is_variant"])
    variants = sum(1 for r in rows if r["is_variant"])
    price_report, mismatches = [], 0
    would_create = would_enrich = 0
    for r in rows:
        key = sku_catalog.catalog_key("Omisell", r["omisell_shop_id"], r["seller_sku"])
        ex = existing.get(key)
        if ex:
            would_enrich += 1
        else:
            would_create += 1
        if ex and ex.source_level == "order_derived" and ex.rsp_price:
            verdict = cs.compare_price(r.get("price"), ex.rsp_price)
            if verdict == "mismatch":
                mismatches += 1
            if len(price_report) < PRICE_REPORT_CAP:
                price_report.append({
                    "seller_sku": r["seller_sku"],
                    "omisell_shop_id": r["omisell_shop_id"],
                    "platform": r["platform"], "is_variant": r["is_variant"],
                    "catalogue_price": r.get("price"),
                    "price_sale": r.get("price_sale"),
                    "order_derived_rsp": ex.rsp_price,
                    "verdict": verdict})
    return {"rows_normalized": len(rows), "parents": parents,
            "variants": variants, "would_create": would_create,
            "would_enrich": would_enrich,
            "price_compare": {"compared": len(price_report),
                              "mismatches": mismatches,
                              "rows": price_report},
            "guard_note": ("order-derived RSP is NEVER overwritten by "
                           "catalogue price; mismatches flagged "
                           "price_confidence=low in note JSON.")}


@frappe.whitelist(methods=["POST"])
def preview_catalogue_sku_sync(brand, pages=None, page_size=None):
    """READ-ONLY preview: what would a catalogue sync do + price report.
    No writes of any kind."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    pages_n = min(int(pages or DEFAULT_PAGES), MAX_PAGES_HARD)
    psize = min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    out = {"brand": brand, "mode": "preview", "pages_requested": pages_n,
           "page_size": psize, "catalogues_total": None, "pages_fetched": 0}
    try:
        rows = _fetch_rows(client, pages_n, psize, deadline, out)
    except OmisellError as e:
        frappe.throw(_("Catalogue fetch failed: {0}").format(str(e)))
    out.update(_stats(rows, _existing_lookup(rows) if rows else {}))
    out["sample_rows"] = rows[:10]
    return out


@frappe.whitelist(methods=["POST"])
def confirm_catalogue_sku_sync(brand, pages=None, page_size=None, max_rows=None):
    """Catalogue sync: idempotent upserts into EC Marketplace SKU Catalog
    ONLY (hash-gated; order-derived RSP wins; re-run never duplicates)."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    pages_n = min(int(pages or MAX_PAGES_HARD), MAX_PAGES_HARD)
    psize = min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
    cap = min(int(max_rows or DEFAULT_MAX_ROWS), MAX_ROWS_HARD)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    out = {"brand": brand, "mode": "confirm", "pages_requested": pages_n,
           "page_size": psize, "row_cap": cap, "catalogues_total": None,
           "pages_fetched": 0}
    try:
        rows = _fetch_rows(client, pages_n, psize, deadline, out)
    except OmisellError as e:
        frappe.throw(_("Catalogue fetch failed: {0}").format(str(e)))
    if len(rows) > cap:
        out["capped_at"] = cap
        rows = rows[:cap]
    counts = {"created": 0, "enriched": 0, "unchanged": 0, "skipped": 0,
              "errors": 0}
    for r in rows:
        if time.monotonic() > deadline:
            out["timeboxed"] = out.get("timeboxed") or "during_upsert"
            break
        try:
            st = cs.upsert_catalogue_row(brand, r)
            counts[st] = counts.get(st, 0) + 1
        except Exception:
            counts["errors"] += 1
            frappe.log_error(frappe.get_traceback(),
                             "alerts.catalogue_sync %s" % r.get("seller_sku"))
    out["counts"] = counts
    out["rows_processed"] = sum(counts.values())
    out["note"] = ("Idempotent: re-run to continue after a cap/timebox - "
                   "hash-gated upserts never duplicate.")
    return out
