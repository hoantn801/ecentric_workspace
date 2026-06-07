"""Phase D manual endpoints - read-only Omisell ingestion (NO scheduler).

All four: POST + System Manager only (frappe.only_for) + active per-brand
EC Brand Integration Settings required. Returns are sanitized - no token /
key / Authorization material can appear in any response or log.
T0-T3 manual flow per ALERT_CENTER/13_PHASE_D_PLAN.md s6.
"""
import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, nowdate

from ecentric_workspace.alerts.services import action_queue, ingestion
from ecentric_workspace.alerts.services import brand_resolver, dedupe_keys
from ecentric_workspace.alerts.services import omisell_normalizer as norm
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellAuthError, OmisellClient, OmisellError, sanitize)

MAX_WINDOW_SECONDS = 3600  # hard MVP guard on pull_orders
MAX_LIST_PAGES = 20
# Phase D.1 capacity hardening (approved 2026-06-09):
MAX_DETAILS_PER_RUN = 300        # per-run order-detail cap (config-tunable)
MAX_CHUNKS_PER_RUN = 4           # catch-up chunks (<=1h each) per pull_recent run
CIRCUIT_BREAKER_LIMIT = 3        # consecutive failed runs -> brand refused


def chunk_windows(start, end, chunk_seconds=MAX_WINDOW_SECONDS, max_chunks=MAX_CHUNKS_PER_RUN):
    """PURE helper: split [start, end] into <=chunk_seconds windows, capped at
    max_chunks (leftover handled by the next run). start/end = datetimes."""
    from datetime import timedelta
    chunks = []
    cur = start
    while cur < end and len(chunks) < max_chunks:
        nxt = min(cur + timedelta(seconds=chunk_seconds), end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def _details_cap():
    try:
        return int(frappe.conf.get("ec_alerts_pull_max_details") or MAX_DETAILS_PER_RUN)
    except Exception:
        return MAX_DETAILS_PER_RUN


def _pull_disabled():
    try:
        return bool(frappe.conf.get("ec_alerts_pull_disabled"))
    except Exception:
        return True  # fail safe


def _breaker_check(bis):
    if int(bis.consecutive_failures or 0) >= CIRCUIT_BREAKER_LIMIT:
        frappe.throw(_(
            "Circuit breaker OPEN for brand {0}: {1} consecutive failed pulls. "
            "Investigate the ingestion_api_failed alert, then reset "
            "Consecutive Failures to 0 on {2} to re-enable.").format(
                bis.brand, bis.consecutive_failures, bis.name))


def _breaker_record(bis, success):
    bis.reload()
    bis.consecutive_failures = 0 if success else int(bis.consecutive_failures or 0) + 1
    bis.save(ignore_permissions=True)


def _get_bis(brand, require_enabled=True):
    name = frappe.db.get_value("EC Brand Integration Settings",
                               {"brand": brand, "integration_type": "Omisell"}, "name")
    if not name:
        frappe.throw(_("No EC Brand Integration Settings (Omisell) for brand {0}.").format(brand))
    bis = frappe.get_doc("EC Brand Integration Settings", name)
    if require_enabled and not int(bis.enabled or 0):
        frappe.throw(_("Integration for brand {0} is disabled (enabled=0).").format(brand))
    return bis


def _auth_failure(bis, brand):
    bis.credential_status = "Expired"
    bis.save(ignore_permissions=True)
    key = dedupe_keys.missing_credential_key(brand, nowdate().replace("-", ""))
    if not frappe.db.exists("EC Alert", {"dedupe_key": key}):
        frappe.get_doc({
            "doctype": "EC Alert", "alert_type": "Price Compliance",
            "rule_code": "missing_integration_credential", "severity": "Warning",
            "status": "Open", "brand": brand, "source_system": "Omisell",
            "title": "Omisell auth failed for brand %s" % brand,
            "message": "Token exchange / authorization failed. Check the API key "
                       "in EC Brand Integration Settings.",
            "owner_user": brand_resolver.resolve_owner(None, brand),
            "recommended_action": "Notify Only", "dedupe_key": key,
            "detected_at": now_datetime(),
        }).insert(ignore_permissions=True)


def _ingestion_failure_alert(brand, message):
    key = dedupe_keys.ingestion_failed_key(brand, nowdate().replace("-", ""))
    if frappe.db.exists("EC Alert", {"dedupe_key": key}):
        return
    frappe.get_doc({
        "doctype": "EC Alert", "alert_type": "Price Compliance",
        "rule_code": "ingestion_api_failed", "severity": "Warning",
        "status": "Open", "brand": brand, "source_system": "Omisell",
        "title": "Omisell ingestion API failure for brand %s" % brand,
        "message": (message or "")[:500],
        "owner_user": brand_resolver.resolve_owner(None, brand),
        "recommended_action": "Notify Only", "dedupe_key": key,
        "detected_at": now_datetime(),
    }).insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def omisell_probe(brand):
    """T0: auth + 1-result shop list. Proves credential/headers/envelope.
    Writes nothing except token cache + credential_status on the BIS."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    try:
        payload = client.get_shops(page=1, page_size=1)
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        frappe.throw(_("Auth probe failed: {0}").format(str(e)))
    data = (payload or {}).get("data") or {}
    count = data.get("count")
    bis.reload()
    bis.credential_status = "Active"
    bis.save(ignore_permissions=True)
    return {"ok": True, "brand": brand, "shop_count": count,
            "rate_limit_header": client.last_rate_header,
            "auth_scheme": frappe.conf.get("ec_alerts_omisell_auth_scheme") or "Omi"}


@frappe.whitelist(methods=["POST"])
def sync_shop_directory(brand):
    """T1: REPORT-ONLY shop directory. Creates/changes nothing - you map
    shops manually in EC Marketplace Shop and re-run until unmapped is empty."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    shops, page = [], 1
    while page <= MAX_LIST_PAGES:
        payload = client.get_shops(page=page, page_size=50)
        data = (payload or {}).get("data") or {}
        results = data.get("results") or []
        shops += [norm.normalize_shop(s) for s in results]
        if not data.get("next") or not results:
            break
        page += 1
    mapped, unmapped = [], []
    for s in shops:
        row = frappe.db.get_value("EC Marketplace Shop",
                                  {"omisell_shop_id": s["shop_id"]},
                                  ["name", "brand", "status"], as_dict=True)
        if row:
            s.update({"ec_shop": row.name, "ec_brand": row.brand, "ec_status": row.status})
            mapped.append(s)
        else:
            unmapped.append(s)
    return {"brand": brand, "total": len(shops), "mapped": mapped,
            "unmapped": unmapped, "rate_limit_header": client.last_rate_header}


@frappe.whitelist(methods=["POST"])
def pull_one_order(brand, omisell_order_number, capture_golden=0):
    """T2: pull ONE specific order, normalize, ingest, run rules engine.
    capture_golden=1 additionally returns the SANITIZED raw payload so it can
    be saved as the golden file for the Q-D5 semantics check."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    try:
        payload = client.get_order_detail(omisell_order_number)
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        frappe.throw(_("Auth failed: {0}").format(str(e)))
    except OmisellError as e:
        _ingestion_failure_alert(brand, str(e))
        frappe.throw(_("Order fetch failed: {0}").format(str(e)))
    data = (payload or {}).get("data") or {}
    o = norm.normalize_order_detail(data)
    real, reason = norm.is_real_sale(o.get("_status_id"), o.get("_status_name"))
    result = {"brand": brand, "order": o["external_order_id"],
              "status": o["order_status"], "real_sale": real, "status_reason": reason,
              "platform": o["platform"], "omisell_shop_id": o["omisell_shop_id"],
              "lines": len(o["items"]),
              "platform_order_number": o.get("_platform_order_number")}
    if real:
        ing = ingestion.ingest_orders([o])
        queue = action_queue.process_pending_actions()
        result.update({"ingest": ing, "action_queue": queue})
    else:
        result["note"] = "Status excluded by Q-D2 filter - NOT ingested."
    if int(capture_golden or 0):
        result["golden_payload"] = sanitize(data)
    return result


@frappe.whitelist(methods=["POST"])
def pull_orders(brand, updated_from, updated_to):
    """T3: pull an updated-time window. HARD GUARD: window <= 3600 seconds.
    last_sync_at advances ONLY when the whole window succeeds (no failures)."""
    frappe.only_for("System Manager")
    f, t = get_datetime(updated_from), get_datetime(updated_to)
    if not f or not t or t <= f:
        frappe.throw(_("Invalid window."))
    if (t - f).total_seconds() > MAX_WINDOW_SECONDS:
        frappe.throw(_("Window exceeds {0}s (MVP hard guard).").format(MAX_WINDOW_SECONDS))
    if _pull_disabled():
        frappe.throw(_("Pulls are disabled (ec_alerts_pull_disabled is set)."))
    bis = _get_bis(brand)
    _breaker_check(bis)
    client = OmisellClient(bis.name)
    f_ts, t_ts = int(f.timestamp()), int(t.timestamp())

    summary = {"brand": brand, "window": [str(f), str(t)], "listed": 0,
               "ingested": 0, "skipped_status": 0, "skipped_status_detail": {},
               "failed": 0, "results": []}
    headers, page = [], 1
    try:
        while page <= MAX_LIST_PAGES:
            payload = client.get_orders(f_ts, t_ts, page=page)
            data = (payload or {}).get("data") or {}
            results = data.get("results") or []
            headers += results
            if not data.get("next") or not results:
                break
            page += 1
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        frappe.throw(_("Auth failed: {0}").format(str(e)))
    except OmisellError as e:
        _ingestion_failure_alert(brand, str(e))
        frappe.throw(_("Order list failed: {0}").format(str(e)))

    summary["listed"] = len(headers)
    cap = _details_cap()
    if len(headers) > cap:
        summary["capped_at"] = cap
        headers = headers[:cap]
    batch = []
    for h in headers:
        number = h.get("omisell_order_number")
        try:
            detail = (client.get_order_detail(number) or {}).get("data") or {}
        except OmisellAuthError:
            summary["failed"] += 1
            _auth_failure(bis, brand)
            break
        except OmisellError as e:
            summary["failed"] += 1
            frappe.log_error(str(e), "alerts.omisell.pull_orders %s" % number)
            continue
        o = norm.normalize_order_detail(detail)
        real, reason = norm.is_real_sale(o.get("_status_id"), o.get("_status_name"))
        if not real:
            summary["skipped_status"] += 1
            key = "%s|%s" % (o.get("_status_id"), o.get("_status_name"))
            summary["skipped_status_detail"][key] = summary["skipped_status_detail"].get(key, 0) + 1
            continue
        batch.append(o)
    if batch:
        ing = ingestion.ingest_orders(batch)
        summary["results"] = ing
        summary["ingested"] = len([r for r in ing if r.get("status") in ("created", "updated", "unchanged")])
        summary["failed"] += len([r for r in ing if r.get("status") in ("failed", "check_failed")])
        summary["action_queue"] = action_queue.process_pending_actions()
    if summary["failed"] == 0 and not summary.get("capped_at"):
        bis.reload()
        bis.last_sync_at = t
        bis.save(ignore_permissions=True)
        summary["last_sync_at_advanced"] = True
        _breaker_record(bis, success=True)
    else:
        if summary["failed"]:
            _ingestion_failure_alert(brand, "%d failures in window %s..%s" % (summary["failed"], f, t))
            _breaker_record(bis, success=False)
        summary["last_sync_at_advanced"] = False
    return summary


@frappe.whitelist(methods=["POST"])
def pull_recent(brand, max_chunks=None):
    """Phase D.1: MANUAL catch-up - successive <=1h chunks from last_sync_at to
    now, chunk-level checkpointing (last_sync_at advances per successful chunk
    via pull_orders), capped per run. This is the future scheduler body but is
    NOT scheduled - SM-only manual call, double kill switch.
    """
    frappe.only_for("System Manager")
    if _pull_disabled():
        frappe.throw(_("Pulls are disabled (ec_alerts_pull_disabled is set)."))
    # NOTE: ec_alerts_scheduler_disabled intentionally does NOT block manual
    # pulls - it gates scheduler jobs only. Manual = this SM-only endpoint.
    bis = _get_bis(brand)
    _breaker_check(bis)
    start = (get_datetime(bis.last_sync_at) if bis.last_sync_at
             else get_datetime(now_datetime()) - timedelta(hours=1))
    end = get_datetime(now_datetime())
    chunks = chunk_windows(start, end,
                           max_chunks=int(max_chunks or MAX_CHUNKS_PER_RUN))
    run = {"brand": brand, "from": str(start), "to": str(end),
           "chunks_planned": len(chunks), "chunks_done": 0, "summaries": []}
    for cf, ct in chunks:
        s = pull_orders(brand, str(cf), str(ct))
        run["summaries"].append({k: s.get(k) for k in
                                 ("window", "listed", "ingested", "skipped_status",
                                  "failed", "capped_at", "last_sync_at_advanced")})
        if not s.get("last_sync_at_advanced"):
            run["stopped"] = "chunk did not fully succeed (failed or capped) - checkpoint holds"
            break
        run["chunks_done"] += 1
    run["caught_up"] = run["chunks_done"] == len(chunks) and         (not chunks or chunks[-1][1] >= end)
    return run


@frappe.whitelist(methods=["POST"])
def capacity_stats():
    """Phase D.1 row-count measurement (decision: measure first, archive later;
    review trigger ~2M rows for Log+Item combined). Read-only."""
    frappe.only_for("System Manager")
    stats = {dt: frappe.db.count(dt) for dt in
             ("EC Marketplace Order Log", "EC Marketplace Order Item",
              "EC Alert", "EC Alert Action", "EC Automation Pause")}
    stats["log_plus_item"] = stats["EC Marketplace Order Log"] + stats["EC Marketplace Order Item"]
    stats["archive_review_trigger"] = 2000000
    stats["archive_review_due"] = stats["log_plus_item"] >= 2000000
    frappe.logger("alerts").info({"capacity_stats": stats})
    return stats
