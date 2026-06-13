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
import json
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from ecentric_workspace.alerts import permissions as perms
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


# =========================================================================
# Phase 4 (2026-06-13): BACKGROUND catalogue sync. The synchronous confirm
# write path is RETIRED - all catalogue writes now go through a background
# worker tracked by an EC Catalogue Sync Run, with a per-brand lock, a
# cooldown, and order-pull priority.
# =========================================================================
LOCK_TTL = 3900                  # s; > max run budget -> stale lock auto-recovers
DEFAULT_COOLDOWN_MIN = 30
JOB_TIME_BUDGET = 3000           # s; worker page-stream timebox
JOB_RQ_TIMEOUT = 3600


def _lock_key(brand):
    return "ec_catalogue_sync_running_%s" % brand


# Atomic compare-and-delete: only the owner (matching token) releases the lock.
_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end")


def _acquire_lock(brand, token, ttl=None):
    """ATOMIC per-brand lock via Redis SET key token NX EX. Returns True iff
    THIS caller acquired it (no get-then-set TOCTOU). frappe.cache() is a
    redis.Redis subclass; make_key adds the site keyspace prefix."""
    cache = frappe.cache()
    return bool(cache.set(cache.make_key(_lock_key(brand)), token,
                          nx=True, ex=int(ttl or LOCK_TTL)))


def _release_lock(brand, token):
    """Release ONLY if we still own it (token matches) - one worker can never
    release another's lock. Atomic via Lua; best-effort fallback."""
    cache = frappe.cache()
    key = cache.make_key(_lock_key(brand))
    try:
        cache.eval(_RELEASE_LUA, 1, key, token)
    except Exception:
        try:
            if cache.get(key) == (token.encode() if isinstance(token, str) else token):
                cache.delete(key)
        except Exception:
            pass


def _active_run(brand):
    rows = frappe.get_all("EC Catalogue Sync Run",
                          filters={"brand": brand, "status": ["in", ["Queued", "Running"]]},
                          fields=["name"], order_by="creation desc", limit_page_length=1)
    return rows[0]["name"] if rows else None


def _pull_running(brand):
    # reuse api_omisell's pull lock key -> order pull stays higher priority
    from ecentric_workspace.alerts.api_omisell import _running_key
    return frappe.cache().get_value(_running_key(brand))


def _cooldown_minutes():
    try:
        v = frappe.conf.get("ec_alerts_catalogue_cooldown_minutes")
        if v in (None, ""):
            return DEFAULT_COOLDOWN_MIN
        return max(0, int(float(v)))
    except Exception:
        return DEFAULT_COOLDOWN_MIN


def _is_truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _last_run(brand):
    rows = frappe.get_all("EC Catalogue Sync Run", filters={"brand": brand},
                          fields=["name", "status", "cooldown_until"],
                          order_by="creation desc", limit_page_length=1)
    return rows[0] if rows else None


@frappe.whitelist(methods=["POST"])
def trigger_catalogue_sync(brand, force=0, pages=None, max_pages=None,
                           pages_requested=None, page_size=None, max_rows=None,
                           row_cap=None, limit=None, start_page=None,
                           allow_heavy=0):
    """Start a BACKGROUND catalogue sync for a brand. Returns quickly with the
    run id. Gate order (Gate 3): permission -> ATOMIC lock acquire ->
    order-pull-active -> cooldown -> create Queued run -> enqueue. Exactly one
    concurrent run per brand (the lock acquire is atomic SET NX). If the brand's
    order pull is active: NO run, NO enqueue, return OrderPullActive (a result,
    not a run status)."""
    user = frappe.session.user
    if not perms.can_run_catalogue_sync(user, brand):
        frappe.throw(_("You cannot run catalogue sync for brand {0}.").format(brand),
                     frappe.PermissionError)
    force = _is_truthy(force)
    if force and not perms.is_global_supervisor(user):
        frappe.throw(_("Only System Manager can force (bypass cooldown)."),
                     frappe.PermissionError)
    _get_bis(brand)  # validates brand + integration enabled

    # 2. ATOMIC lock acquire (no get-then-set). Loser never enqueues.
    token = frappe.generate_hash(length=24)
    if not _acquire_lock(brand, token):
        return {"status": "AlreadyRunning", "brand": brand,
                "run_id": _active_run(brand),
                "note": "A catalogue sync for this brand is already in progress."}
    try:
        # 3. Order-pull priority: NO run, NO enqueue while pull is active.
        if _pull_running(brand):
            _release_lock(brand, token)
            return {"status": "OrderPullActive", "brand": brand,
                    "note": "Order ingestion has priority; retry shortly."}

        # 4. Cooldown (force bypasses; SM-only force already checked).
        last = _last_run(brand)
        if not force and last and last.get("cooldown_until"):
            if get_datetime(now_datetime()) < get_datetime(last["cooldown_until"]):
                _release_lock(brand, token)
                return {"status": "Cooldown", "brand": brand, "run_id": last["name"],
                        "cooldown_until": str(last["cooldown_until"]),
                        "note": "Within cooldown; use force=1 (System Manager) to override."}

        # 5. Create Queued run.
        p = cs.resolve_confirm_params(pages=pages, max_pages=max_pages,
                                      pages_requested=pages_requested,
                                      page_size=page_size, max_rows=max_rows,
                                      row_cap=row_cap, limit=limit,
                                      start_page=start_page, allow_heavy=allow_heavy)
        cooldown_until = add_to_date(now_datetime(), minutes=_cooldown_minutes())
        run = frappe.get_doc({
            "doctype": "EC Catalogue Sync Run", "brand": brand,
            "requested_by": user, "trigger_type": "Manual", "status": "Queued",
            "cooldown_until": cooldown_until, "lock_key": _lock_key(brand),
            "summary_json": json.dumps({"params": p, "force": force, "token": token}),
        }).insert(ignore_permissions=True)

        # 6. Enqueue (pass the ownership token so the worker releases only ours).
        try:
            job = frappe.enqueue(
                "ecentric_workspace.alerts.api_catalogue_sync.catalogue_sync_job",
                queue="long", timeout=JOB_RQ_TIMEOUT,
                job_name="catalogue_sync_%s" % brand, brand=brand, run=run.name,
                params=p, lock_token=token)
        except Exception:
            _release_lock(brand, token)   # don't lock the brand out
            run.db_set("status", "Failed")
            run.db_set("error_message", "enqueue failed")
            raise
        run.db_set("job_id", getattr(job, "id", None))
        return {"status": "Queued", "brand": brand, "run_id": run.name,
                "cooldown_until": str(cooldown_until)}
    except Exception:
        _release_lock(brand, token)       # never leak the lock on an early error
        raise


@frappe.whitelist(methods=["POST"])
def confirm_catalogue_sku_sync(brand, force=0, pages=None, max_pages=None,
                               pages_requested=None, page_size=None, max_rows=None,
                               row_cap=None, limit=None, start_page=None,
                               allow_heavy=0):
    """DEPRECATED alias (Gate 1, 2026-06-13). The current production UI may
    still call confirm; it now delegates to the background trigger and returns
    the new run response (run_id + status). NO synchronous catalogue write
    happens here. The canonical endpoint is trigger_catalogue_sync; the
    frontend may drop this alias in a later UI phase."""
    return trigger_catalogue_sync(
        brand, force=force, pages=pages, max_pages=max_pages,
        pages_requested=pages_requested, page_size=page_size, max_rows=max_rows,
        row_cap=row_cap, limit=limit, start_page=start_page, allow_heavy=allow_heavy)


def catalogue_sync_job(brand, run, params=None, lock_token=None):
    """Background worker (NOT whitelisted, NOT scheduled). Page-streams the
    catalogue, upserts into SKU Catalog (idempotent, hash-gated, order-derived
    RSP never overwritten), persists progress + final result to the run, and
    ALWAYS releases the per-brand lock in finally (after persisting result) -
    using the ownership token, so it can never release another run's lock."""
    doc = frappe.get_doc("EC Catalogue Sync Run", run)
    # capture the ownership token NOW (before summary_json is overwritten below)
    token = lock_token
    if token is None:
        try:
            token = json.loads(doc.summary_json or "{}").get("token")
        except Exception:
            token = None
    p = params or cs.resolve_confirm_params()
    counts = {"created": 0, "enriched": 0, "unchanged": 0, "skipped": 0,
              "errors": 0}
    processed = 0
    page = p["start_page"]
    last = p["start_page"] + p["effective_pages_requested"] - 1
    total = None
    state = "Completed"
    err = None
    deadline = time.monotonic() + JOB_TIME_BUDGET
    try:
        doc.db_set("status", "Running")
        doc.db_set("started_at", now_datetime())
        client = OmisellClient(_get_bis(brand).name)
        stopped = False
        while page <= last and not stopped:
            if time.monotonic() > deadline:
                state = "Partial"
                break
            page_rows, page_total, more = _fetch_page(client, page,
                                                      p["effective_page_size"])
            if total is None:
                total = page_total
                doc.db_set("total_items", total)
            for r in page_rows:
                if processed >= p["effective_row_cap"] or time.monotonic() > deadline:
                    state = "Partial"
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
            doc.db_set("processed_items", processed)
            doc.db_set("inserted", counts["created"])
            doc.db_set("updated", counts["enriched"])
            doc.db_set("skipped", counts["unchanged"] + counts["skipped"])
            doc.db_set("failed", counts["errors"])
            if stopped:
                break
            if not more:
                break
            page += 1
        if counts["errors"] and state == "Completed":
            state = "Partial"
    except Exception as e:
        state = "Failed"
        err = str(e)[:500]
        frappe.log_error(frappe.get_traceback(), "alerts.catalogue_sync_job %s" % brand)
    finally:
        # persist result BEFORE releasing the lock
        try:
            doc.db_set("status", state)
            doc.db_set("finished_at", now_datetime())
            if err:
                doc.db_set("error_message", err)
            doc.db_set("summary_json", json.dumps({
                "params": p, "counts": counts, "processed": processed,
                "total": total, "next_page": page if state == "Partial" else None}))
        finally:
            # release ONLY our lock (token compare-and-del) - captured above.
            if token:
                _release_lock(brand, token)
    return {"run": run, "status": state, "counts": counts}


@frappe.whitelist()
def catalogue_sync_status(run=None, brand=None):
    """Read a run's status (by run id) or the latest run for a brand. Brand-
    scoped permission (same as trigger)."""
    if run:
        doc = frappe.get_doc("EC Catalogue Sync Run", run)
        if not perms.can_run_catalogue_sync(frappe.session.user, doc.brand):
            frappe.throw(_("Not allowed."), frappe.PermissionError)
        return _run_dict(doc)
    if brand:
        if not perms.can_run_catalogue_sync(frappe.session.user, brand):
            frappe.throw(_("Not allowed."), frappe.PermissionError)
        last = _last_run(brand)
        if not last:
            return {"brand": brand, "status": None}
        return _run_dict(frappe.get_doc("EC Catalogue Sync Run", last["name"]))
    frappe.throw(_("run or brand is required."))


def _run_dict(doc):
    return {"run_id": doc.name, "brand": doc.brand, "status": doc.status,
            "trigger_type": doc.trigger_type, "requested_by": doc.requested_by,
            "started_at": str(doc.started_at) if doc.started_at else None,
            "finished_at": str(doc.finished_at) if doc.finished_at else None,
            "total_items": doc.total_items, "processed_items": doc.processed_items,
            "inserted": doc.inserted, "updated": doc.updated,
            "skipped": doc.skipped, "failed": doc.failed,
            "cooldown_until": str(doc.cooldown_until) if doc.cooldown_until else None,
            "error_message": doc.error_message}
