"""G2.2 - catalogue/list -> SKU Catalog: preview + confirm endpoints.

Both SM-only POST (they hit the live Omisell API, same trust level as
api_omisell). GET-only against Omisell via the frozen client chokepoint.

  * preview_catalogue_sku_sync: fetch + normalize + PRICE REPORT. Writes
    NOTHING (no DB write of any kind in this module).
  * confirm_catalogue_sku_sync: page-by-page fetch + idempotent upserts that
    write ONLY to EC Marketplace SKU Catalog (services.catalogue_sync;
    order-derived RSP always wins - see price guard there).

HOTFIX 2026-06-12 (LOF Bad Gateway): confirm previously defaulted to 40
pages and IGNORED caller caps sent as pages_requested/row_cap/limit - a
heavy synchronous run blew the gunicorn timeout and took the bench down.
Now: all param aliases honored + echoed back (effective_*), sync-safe
defaults (2 pages / 300 rows), hard 5-page sync cap unless allow_heavy=1,
50s time budget with page-streaming so a stop returns timeboxed=true +
next_page + rows_processed (partial progress is safe - upserts are
hash-gated idempotent; re-run with start_page=next_page to continue).

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

TIME_BUDGET_SECONDS = 50     # same reasoning as api_omisell.SYNC_TIME_BUDGET
PRICE_REPORT_CAP = 200


def _fetch_page(client, page, page_size):
    payload = client.get_catalogues(page=page, page_size=page_size)
    data = (payload or {}).get("data") or {}
    results = data.get("results") or []
    rows = []
    for c in results:
        rows.extend(cs.normalize_catalogue(c))
    return rows, data.get("count"), bool(data.get("next") and results)


def _existing_lookup(rows):
    """Read-only map catalog_key -> {name, rsp_price, source_level}."""
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
def preview_catalogue_sku_sync(brand, pages=None, max_pages=None,
                               pages_requested=None, page_size=None,
                               start_page=None, allow_heavy=0):
    """READ-ONLY preview: what would a catalogue sync do + price report.
    No writes of any kind. Honors the same param aliases/caps as confirm."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    p = cs.resolve_confirm_params(pages=pages, max_pages=max_pages,
                                  pages_requested=pages_requested,
                                  page_size=page_size, start_page=start_page,
                                  allow_heavy=allow_heavy)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    out = dict(p, brand=brand, mode="preview", catalogues_total=None,
               pages_fetched=0)
    rows, page = [], p["start_page"]
    last = p["start_page"] + p["effective_pages_requested"] - 1
    try:
        while page <= last:
            if time.monotonic() > deadline:
                out["timeboxed"] = True
                out["next_page"] = page
                break
            page_rows, total, more = _fetch_page(client, page,
                                                 p["effective_page_size"])
            rows.extend(page_rows)
            out["catalogues_total"] = (total if out["catalogues_total"] is None
                                       else out["catalogues_total"])
            out["pages_fetched"] += 1
            if not more:
                break
            page += 1
    except OmisellError as e:
        frappe.throw(_("Catalogue fetch failed: {0}").format(str(e)))
    out["rate_limit_header"] = client.last_rate_header
    out.update(_stats(rows, _existing_lookup(rows) if rows else {}))
    out["sample_rows"] = rows[:10]
    return out


@frappe.whitelist(methods=["POST"])
def confirm_catalogue_sku_sync(brand, pages=None, max_pages=None,
                               pages_requested=None, page_size=None,
                               max_rows=None, row_cap=None, limit=None,
                               start_page=None, allow_heavy=0):
    """Catalogue sync: page-streaming idempotent upserts into EC Marketplace
    SKU Catalog ONLY. Echoes effective_* params; stops safely on row cap or
    time budget with next_page for resume (re-run never duplicates)."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    p = cs.resolve_confirm_params(pages=pages, max_pages=max_pages,
                                  pages_requested=pages_requested,
                                  page_size=page_size, max_rows=max_rows,
                                  row_cap=row_cap, limit=limit,
                                  start_page=start_page,
                                  allow_heavy=allow_heavy)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    out = dict(p, brand=brand, mode="confirm", catalogues_total=None,
               pages_fetched=0)
    counts = {"created": 0, "enriched": 0, "unchanged": 0, "skipped": 0,
              "errors": 0}
    processed = 0
    page = p["start_page"]
    last = p["start_page"] + p["effective_pages_requested"] - 1
    stopped = False
    try:
        while page <= last and not stopped:
            if time.monotonic() > deadline:
                out["timeboxed"] = True
                out["next_page"] = page
                break
            page_rows, total, more = _fetch_page(client, page,
                                                 p["effective_page_size"])
            out["catalogues_total"] = (total if out["catalogues_total"] is None
                                       else out["catalogues_total"])
            for r in page_rows:
                if processed >= p["effective_row_cap"]:
                    out["capped_at"] = p["effective_row_cap"]
                    out["next_page"] = page  # page partially done; re-run is
                    stopped = True           # idempotent so overlap is safe
                    break
                if time.monotonic() > deadline:
                    out["timeboxed"] = True
                    out["next_page"] = page
                    stopped = True
                    break
                try:
                    st = cs.upsert_catalogue_row(brand, r)
                    counts[st] = counts.get(st, 0) + 1
                except Exception:
                    counts["errors"] += 1
                    frappe.log_error(frappe.get_traceback(),
                                     "alerts.catalogue_sync %s" % r.get("seller_sku"))
                processed += 1
            if stopped:
                break
            out["pages_fetched"] += 1
            if not more:
                out["complete"] = True
                break
            page += 1
        else:
            if not stopped:
                out["complete"] = out.get("complete", True)
    except OmisellError as e:
        frappe.throw(_("Catalogue fetch failed: {0}").format(str(e)))
    out["rate_limit_header"] = client.last_rate_header
    out["counts"] = counts
    out["rows_processed"] = processed
    out["note"] = ("Idempotent: hash-gated upserts never duplicate - resume "
                   "with start_page=next_page after a cap/timebox.")
    return out
