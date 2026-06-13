"""Phase D manual endpoints - read-only Omisell ingestion (NO scheduler).

All four: POST + System Manager only (frappe.only_for) + active per-brand
EC Brand Integration Settings required. Returns are sanitized - no token /
key / Authorization material can appear in any response or log.
T0-T3 manual flow per ALERT_CENTER/13_PHASE_D_PLAN.md s6.
"""
import json
import time
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, nowdate

from ecentric_workspace.alerts.services import action_queue, ingestion
from ecentric_workspace.alerts.services import brand_resolver, dedupe_keys
from ecentric_workspace.alerts.services import order_retry
from ecentric_workspace.alerts.services import subwindow_planner as swp
from ecentric_workspace.alerts.services import omisell_normalizer as norm
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellAuthError, OmisellClient, OmisellError, sanitize)
from ecentric_workspace.alerts.services.time_windows import epoch_in_tz, utc_str

MAX_WINDOW_SECONDS = 3600  # hard MVP guard on pull_orders
MAX_LIST_PAGES = 20
# Phase D.1 capacity hardening (approved 2026-06-09):
MAX_DETAILS_PER_RUN = 300        # per-run order-detail cap (config-tunable)
MAX_CHUNKS_PER_RUN = 4           # catch-up chunks (<=1h each) per pull_recent run
MAX_OVERLAP_CHUNKS = 12          # hard cap when the overlap re-scan widens the window
CIRCUIT_BREAKER_LIMIT = 3        # consecutive failed runs -> brand refused
# Hotfix 2026-06-09 (bench 502 incident): client pacing (~1s/call) x hundreds
# of detail GETs cannot run inside a synchronous web request (gunicorn worker
# timeout -> worker killed -> Bad Gateway). Hence: timeboxes + background job.
SYNC_TIME_BUDGET = 50            # s - hard timebox for DIRECT pull_orders calls
JOB_TIME_BUDGET = 3000           # s - timebox inside the background job
JOB_RQ_TIMEOUT = 3600            # rq hard kill above the budget
RUNNING_FLAG_TTL = 3900          # s - per-brand concurrent-run lock


def _running_key(brand):
    return "ec_alerts_pull_running_%s" % brand


def _last_run_key(brand):
    return "ec_alerts_pull_last_%s" % brand


def chunk_windows(start, end, chunk_seconds=MAX_WINDOW_SECONDS, max_chunks=MAX_CHUNKS_PER_RUN):
    """PURE helper: split [start, end] into <=chunk_seconds windows, capped at
    max_chunks (leftover handled by the next run). start/end = datetimes."""
    chunks = []
    cur = start
    while cur < end and len(chunks) < max_chunks:
        nxt = min(cur + timedelta(seconds=chunk_seconds), end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def _site_timezone():
    """Site tz from System Settings; fail-safe to Asia/Ho_Chi_Minh (the only
    deployed site tz). Read per call - cheap, and a tz change needs no restart."""
    try:
        return (frappe.db.get_single_value("System Settings", "time_zone")
                or "Asia/Ho_Chi_Minh")
    except Exception:
        return "Asia/Ho_Chi_Minh"


def _to_epoch(dt):
    """TZ-FIX 2026-06-10: SITE-TZ-aware UTC epoch for Omisell order/list
    updated_from/updated_to. Replaces int(naive.timestamp()), which used the
    SERVER timezone (UTC on Frappe Cloud) and shifted every window ~7h into
    the future (diagnostic 46, drift_seconds = -25200). Pure conversion lives
    in services.time_windows.epoch_in_tz."""
    return epoch_in_tz(get_datetime(dt), _site_timezone())


def _details_cap():
    try:
        return int(frappe.conf.get("ec_alerts_pull_max_details") or MAX_DETAILS_PER_RUN)
    except Exception:
        return MAX_DETAILS_PER_RUN


# --- adaptive sub-window config (scalability mini-phase 2026-06-14) ----------
def _min_subwindow_seconds():
    try:
        v = frappe.conf.get("ec_alerts_pull_min_subwindow_seconds")
        return max(1, int(float(v))) if v not in (None, "") else swp.DEFAULT_MIN_SUBWINDOW_SECONDS
    except Exception:
        return swp.DEFAULT_MIN_SUBWINDOW_SECONDS


def _max_split_depth():
    try:
        v = frappe.conf.get("ec_alerts_pull_max_split_depth")
        return max(0, int(float(v))) if v not in (None, "") else swp.DEFAULT_MAX_SPLIT_DEPTH
    except Exception:
        return swp.DEFAULT_MAX_SPLIT_DEPTH


def _brand_budget_seconds():
    try:
        v = frappe.conf.get("ec_alerts_pull_brand_budget_seconds")
        return max(1, int(float(v))) if v not in (None, "") else swp.DEFAULT_BRAND_BUDGET_SECONDS
    except Exception:
        return swp.DEFAULT_BRAND_BUDGET_SECONDS


DISABLED_VALUES = {"1", "true", "yes", "on"}
ENABLED_VALUES = {"0", "false", "no", "off", ""}


def parse_disabled_flag(value):
    """PURE safe boolean parser (hotfix 2026-06-09: bool("0") is True in
    Python - a site_config value of "0" wrongly kept pulls disabled).
    Disabled ONLY for: 1, "1", true, "true", "yes", "on" (case/space
    insensitive). Everything else - 0, "0", false, "false", "no", "off",
    empty string, None/missing - means NOT disabled."""
    if value is True:
        return True
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in DISABLED_VALUES


def _pull_disabled():
    try:
        return parse_disabled_flag(frappe.conf.get("ec_alerts_pull_disabled"))
    except Exception:
        return True  # fail safe: cannot READ config -> do nothing


def _skip_orders():
    """Manual poison-pill list (diag hotfix 2026-06-10): site_config
    ec_alerts_pull_skip_orders = ["OMI-...", ...]. Orders listed here are
    skipped (reported as skipped_manual) instead of failing the chunk -
    lets a window with known-bad orders complete and advance the checkpoint.
    Default empty; every use is visible in the run summary."""
    try:
        v = frappe.conf.get("ec_alerts_pull_skip_orders") or []
        return {str(x).strip() for x in v} if isinstance(v, (list, tuple)) else set()
    except Exception:
        return set()


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


def _format_failure_context(message, context=None):
    """Actionable, secret-free alert body (observability hotfix 2026-06-10)."""
    lines = [message or ""]
    c = context or {}
    if c.get("window"):
        lines.append("window: %s -> %s" % tuple(c["window"]))
    lines.append("listed=%s ingested=%s skipped_status=%s failed=%s" % (
        c.get("listed", "?"), c.get("ingested", "?"),
        c.get("skipped_status", "?"), c.get("failed", "?")))
    if c.get("failed_order_numbers"):
        lines.append("failed orders: %s" % ", ".join(
            str(x) for x in c["failed_order_numbers"][:10]))
    for num, err in list((c.get("failed_error_summary") or {}).items())[:10]:
        lines.append("  %s: %s" % (num, err))
    if c.get("skipped_status_detail"):
        lines.append("skipped statuses: " + "; ".join(
            "%s x%s" % (k, v) for k, v in c["skipped_status_detail"].items()))
    if c.get("skipped_manual"):
        lines.append("manually skipped (config): %s" % ", ".join(
            str(x) for x in c["skipped_manual"]))
    return "\n".join(lines)[:1800]


def _ingestion_failure_alert(brand, message, context=None):
    body = _format_failure_context(message, context)
    key = dedupe_keys.ingestion_failed_key(brand, nowdate().replace("-", ""))
    existing = frappe.db.get_value("EC Alert", {"dedupe_key": key},
                                   ["name", "status"], as_dict=True)
    if existing:
        # daily-deduped: refresh the body with the LATEST diagnostics while
        # the alert is still being worked (track_changes keeps history)
        if existing.status in ("Open", "In Review"):
            doc = frappe.get_doc("EC Alert", existing.name)
            doc.message = body
            doc.save(ignore_permissions=True)
        return
    frappe.get_doc({
        "doctype": "EC Alert", "alert_type": "Price Compliance",
        "rule_code": "ingestion_api_failed", "severity": "Warning",
        "status": "Open", "brand": brand, "source_system": "Omisell",
        "title": "Omisell ingestion API failure for brand %s" % brand,
        "message": body,
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


def _new_summary(brand, cf, ct, f_ts, t_ts):
    return {"brand": brand, "window": [str(cf), str(ct)],
            "epoch_window": [f_ts, t_ts],
            "utc_window": [utc_str(f_ts), utc_str(t_ts)], "listed": 0,
            "ingested": 0, "skipped_status": 0, "skipped_status_detail": {},
            "failed": 0, "failed_order_numbers": [], "failed_error_summary": {},
            "queued_for_retry": 0, "unqueued_failures": 0,
            "listed_order_numbers": [], "skipped_manual": [], "results": []}


def _slim_summary(s):
    return {k: s.get(k) for k in (
        "window", "epoch_window", "utc_window", "listed", "ingested",
        "skipped_status", "skipped_manual", "failed", "failed_order_numbers",
        "failed_error_summary", "listed_order_numbers", "capped_at",
        "timeboxed", "queued_for_retry", "unqueued_failures", "elapsed_seconds")}


# ===== TIER 1: list-only (NO detail, NO DB write, NO checkpoint) =============
def list_window_headers(client, f_ts, t_ts, budget=None, t0=None):
    """TIER 1: list order headers for an epoch window. Paginated up to
    MAX_LIST_PAGES. Pure read - never fetches a detail, writes the DB, or
    touches the checkpoint. Returns listed/headers/pages/timeboxed. Any
    OmisellError/OmisellAuthError from the list call propagates to the caller."""
    t0 = t0 if t0 is not None else time.monotonic()
    headers, page, timeboxed = [], 1, None
    while page <= MAX_LIST_PAGES:
        if budget is not None and time.monotonic() - t0 > budget:
            timeboxed = "during_list"
            break
        payload = client.get_orders(f_ts, t_ts, page=page)
        data = (payload or {}).get("data") or {}
        results = data.get("results") or []
        headers += results
        if not data.get("next") or not results:
            break
        page += 1
    return {"listed": len(headers), "headers": headers, "pages": page,
            "timeboxed": timeboxed}


def probe_window_count(client, f_ts, t_ts):
    """TIER-1 PROBE (NO side effect): a single list call (page_size=1) returning
    the window's TOTAL order count via data['count']. The orchestrator uses this
    to decide split-vs-process WITHOUT fetching details or writing anything.
    Returns None if the API omits 'count' (caller falls back to a full list)."""
    payload = client.get_orders(f_ts, t_ts, page=1, page_size=1)
    data = (payload or {}).get("data") or {}
    cnt = data.get("count")
    return int(cnt) if cnt is not None else None


# ===== shared detail+ingest+retry (NO checkpoint, NO cap decision) ==========
def _process_headers(brand, bis, client, headers, budget, t0, summary, unqueued):
    """Fetch details for the given headers, ingest the real sales, and durably
    QUEUE transient failures into EC Order Retry. Mutates summary + unqueued.
    NEVER lists, decides cap, or writes the checkpoint. Returns a stop signal:
    None (ok) | 'auth' (system-level, stop) | 'timeboxed'."""
    skip_list = _skip_orders()
    batch, stop = [], None
    for h in headers:
        if time.monotonic() - t0 > budget:
            summary["timeboxed"] = summary.get("timeboxed") or "during_details"
            stop = "timeboxed"
            break
        number = h.get("omisell_order_number")
        if number and str(number).strip() in skip_list:
            summary["skipped_manual"].append(number)
            continue
        try:
            detail = (client.get_order_detail(number) or {}).get("data") or {}
        except OmisellAuthError as e:
            summary["failed"] += 1
            summary["failed_order_numbers"].append(number)
            summary["failed_error_summary"][str(number)] = ("auth: %s" % e)[:140]
            _auth_failure(bis, brand)
            unqueued.append(number)
            stop = "auth"
            break
        except OmisellError as e:
            summary["failed"] += 1
            summary["failed_order_numbers"].append(number)
            summary["failed_error_summary"][str(number)] = str(e)[:140]
            frappe.log_error(str(e), "alerts.omisell.process %s" % number)
            if order_retry.upsert(brand, number, e):
                summary["queued_for_retry"] += 1
            else:
                unqueued.append(number)
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
        for r in ing:
            if r.get("status") in ("failed", "check_failed"):
                summary["failed"] += 1
                num = r.get("external_order_id") or r.get("order")
                summary["failed_order_numbers"].append(num)
                summary["failed_error_summary"][str(num)] = "ingest_%s (see Error Log)" % r.get("status")
                if order_retry.upsert(brand, num, "ingest_%s" % r.get("status")):
                    summary["queued_for_retry"] += 1
                else:
                    unqueued.append(num)
        summary["action_queue"] = action_queue.process_pending_actions()
    return stop


# ===== TIER 2: process ONE window confirmed within cap (NO checkpoint) =======
def process_complete_window(brand, bis, client, cf, ct, budget, t0):
    """TIER 2: process a window the orchestrator has probed to be within cap.
    SHARED-BOUNDARY: updated_from=epoch(cf), updated_to=epoch(ct) UNCHANGED (no
    +/-1) - adjacent leaves share the seam so no order is dropped under either
    Omisell inclusivity; order_key dedupe absorbs any seam double-read (see
    subwindow_planner.api_upper_bound). Re-lists authoritatively; if it STILL
    exceeds cap (stale probe) returns SPLIT_REQUIRED with NO side effect (no
    details, no DB, no checkpoint). Otherwise fetches + ingests + queues
    transient failures. NEVER writes the checkpoint - the orchestrator owns it.
    Returns (state, summary, unqueued). Same bounds as the probe (binding 6)."""
    f_ts = _to_epoch(cf)
    t_ts = swp.api_upper_bound(_to_epoch(ct))
    summary = _new_summary(brand, cf, ct, f_ts, t_ts)
    cap = _details_cap()
    try:
        listing = list_window_headers(client, f_ts, t_ts, budget=budget, t0=t0)
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        summary["error"] = ("auth(list): %s" % e)[:160]
        return swp.PROCESSING_FAILED, summary, []
    except OmisellError as e:
        summary["error"] = ("list: %s" % e)[:160]
        return swp.PROCESSING_FAILED, summary, []
    summary["listed"] = listing["listed"]
    summary["listed_order_numbers"] = [h.get("omisell_order_number")
                                       for h in listing["headers"][:20]]
    if listing["timeboxed"]:
        summary["timeboxed"] = listing["timeboxed"]
        return swp.BUDGET_EXHAUSTED, summary, []
    if listing["listed"] > cap:
        summary["capped_at"] = cap
        return swp.SPLIT_REQUIRED, summary, []        # probe result, no side effect
    unqueued = []
    stop = _process_headers(brand, bis, client, listing["headers"], budget, t0,
                            summary, unqueued)
    summary["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    summary["unqueued_failures"] = len(unqueued)
    if stop == "timeboxed":
        return swp.BUDGET_EXHAUSTED, summary, unqueued
    if stop == "auth":
        return swp.PROCESSING_FAILED, summary, unqueued
    if unqueued:                                       # retry persistence failed
        return swp.RETRY_PERSISTENCE_FAILED, summary, unqueued
    return swp.COMPLETED, summary, unqueued


def _advance_checkpoint(bis, dt):
    """MONOTONIC checkpoint write, OWNED by the orchestrator, called ONLY at a
    COMPLETED leaf's end. Never moves last_sync_at backward."""
    bis.reload()
    prev = get_datetime(bis.last_sync_at) if bis.last_sync_at else None
    target = get_datetime(dt)
    bis.last_sync_at = prev if (prev and prev > target) else target
    bis.save(ignore_permissions=True)


def _minimum_window_alert(brand, cf, ct, listed, cap):
    """Actionable, DEDUPED alert for a minimum-width window that STILL exceeds
    cap (cannot split further -> needs Omisell pagination/cursor). Dedupe key =
    brand + window + cap + date, so a stuck window raises ONE alert, not one per
    scheduler cycle. Reuses the existing SYSTEM rule_code ingestion_api_failed
    (no DocType enum change); distinct title/body marks it as a capacity limit."""
    win = "%s_%s" % (_to_epoch(cf), _to_epoch(ct))
    key = dedupe_keys.min_window_capped_key(brand, win, cap, nowdate().replace("-", ""))
    if frappe.db.exists("EC Alert", {"dedupe_key": key}):
        return
    frappe.get_doc({
        "doctype": "EC Alert", "alert_type": "Price Compliance",
        "rule_code": "ingestion_api_failed", "severity": "Warning",
        "status": "Open", "brand": brand, "source_system": "Omisell",
        "title": "Omisell pull stuck: minimum sub-window over cap (brand %s)" % brand,
        "message": ("Minimum sub-window [%s, %s) lists %s orders > cap %s and "
                    "cannot be split further (min=%ss, max_depth=%s). The pull "
                    "checkpoint is HELD before this window. Needs Omisell "
                    "pagination/cursor support to drain it." % (
                        cf, ct, listed, cap, _min_subwindow_seconds(),
                        _max_split_depth())),
        "owner_user": brand_resolver.resolve_owner(None, brand),
        "recommended_action": "Notify Only", "dedupe_key": key,
        "detected_at": now_datetime(),
    }).insert(ignore_permissions=True)


# ===== TIER 3: adaptive orchestrator (OWNS the checkpoint) ===================
def pull_window_adaptive(brand, bis, client, cf, ct, deadline, depth, tele):
    """TIER 3: probe a window's order count; if > cap divide [cf, ct) at the
    midpoint (left then right) until each leaf is within cap, then process the
    leaf and advance the checkpoint to the LEAF end (monotonic). Bounded by a
    shared brand `deadline` (monotonic seconds) checked BEFORE each sub-window.
    Returns one of subwindow_planner's stop states. Checkpoint is advanced ONLY
    on a COMPLETED leaf - never on a parent (a capped parent is just a probe)."""
    tele["split_depth"] = max(tele["split_depth"], depth)
    if time.monotonic() >= deadline:
        tele["budget_exhausted"] = True
        tele["stop_reason"] = swp.BUDGET_EXHAUSTED
        return swp.BUDGET_EXHAUSTED

    width = swp.window_seconds(cf, ct)
    f_ts = _to_epoch(cf)
    t_ts = swp.api_upper_bound(_to_epoch(ct))      # SAME bounds as process (binding 6)
    # PROBE (no side effect)
    try:
        count = probe_window_count(client, f_ts, t_ts)
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        tele["stop_reason"] = swp.PROCESSING_FAILED
        tele["error"] = ("auth(probe): %s" % e)[:120]
        _breaker_record(bis, success=False)
        return swp.PROCESSING_FAILED
    except OmisellError as e:
        tele["stop_reason"] = swp.PROCESSING_FAILED
        tele["error"] = ("list(probe): %s" % e)[:120]
        _ingestion_failure_alert(brand, "probe list failure: %s" % e,
                                 context={"window": [str(cf), str(ct)]})
        _breaker_record(bis, success=False)
        return swp.PROCESSING_FAILED

    cap = _details_cap()
    if count is not None and count > cap:
        return _split_or_stuck(brand, bis, client, cf, ct, deadline, depth, tele,
                               width, count, cap)

    # within cap (or count unknown) -> process this leaf fully
    t0 = time.monotonic()
    budget = max(0.0, deadline - t0)
    state, summary, unqueued = process_complete_window(brand, bis, client, cf, ct,
                                                       budget, t0)
    tele["leaf_summaries"].append(_slim_summary(summary))
    if state == swp.SPLIT_REQUIRED:                    # stale probe under-counted
        return _split_or_stuck(brand, bis, client, cf, ct, deadline, depth, tele,
                               width, summary.get("listed"), cap)
    if state == swp.COMPLETED:
        tele["subwindows_processed"] += 1
        _advance_checkpoint(bis, ct)                   # monotonic, LEAF end only
        tele["checkpoint_advanced_to"] = str(ct)
        _breaker_record(bis, success=True)
        return swp.COMPLETED
    if state == swp.BUDGET_EXHAUSTED:
        tele["budget_exhausted"] = True
        tele["stop_reason"] = swp.BUDGET_EXHAUSTED
        return swp.BUDGET_EXHAUSTED
    # RETRY_PERSISTENCE_FAILED or PROCESSING_FAILED -> hold checkpoint, breaker
    tele["stop_reason"] = state
    _ingestion_failure_alert(brand, "%s in window %s..%s" % (state, cf, ct),
                             context=summary)
    _breaker_record(bis, success=False)
    return state


def _split_or_stuck(brand, bis, client, cf, ct, deadline, depth, tele,
                    width, listed, cap):
    """Window exceeds cap: split (left then right) if width > min AND
    depth < max_depth; otherwise it is a minimum_window_capped dead-end - stop
    safe, do NOT advance the checkpoint, raise ONE deduped alert."""
    if swp.can_split(width, depth, _min_subwindow_seconds(), _max_split_depth()):
        mid = swp.split_point(cf, ct)
        tele["subwindows_seen"] += 1                   # parent probe, NOT processed
        left = pull_window_adaptive(brand, bis, client, cf, mid, deadline,
                                    depth + 1, tele)
        if left != swp.COMPLETED:
            return left                                # checkpoint holds at left's end
        return pull_window_adaptive(brand, bis, client, mid, ct, deadline,
                                    depth + 1, tele)
    tele["minimum_window_reached"] = True
    tele["stop_reason"] = swp.MINIMUM_WINDOW_CAPPED
    _minimum_window_alert(brand, cf, ct, listed, cap)
    return swp.MINIMUM_WINDOW_CAPPED


@frappe.whitelist(methods=["POST"])
def pull_orders(brand, updated_from, updated_to, time_budget=None):
    """T3: pull an updated-time window. HARD GUARD: window <= 3600 seconds.
    last_sync_at advances ONLY when the whole window fully succeeds (no
    failures, no cap, no timebox). time_budget seconds: direct web calls
    default to SYNC_TIME_BUDGET (50s) so a request can never approach the
    gunicorn worker timeout; the background job passes JOB_TIME_BUDGET."""
    frappe.only_for("System Manager")
    budget = float(time_budget or SYNC_TIME_BUDGET)
    t0 = time.monotonic()
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
    # TZ-FIX 2026-06-10: site-tz-aware conversion (was int(f.timestamp()),
    # which used SERVER tz = UTC and queried ~7h in the future).
    f_ts, t_ts = _to_epoch(f), _to_epoch(t)

    # Back-compat single-window endpoint: now reuses the TIER-1 lister + the
    # shared TIER-2 detail/ingest processor (no copy-paste) while preserving its
    # exact contract (truncate-to-cap, process, advance checkpoint iff fully
    # successful). The adaptive job path does NOT call this; it uses
    # pull_window_adaptive. NOTE: this endpoint keeps the legacy inclusive epoch
    # (no half-open seam) so direct SM behavior is unchanged.
    summary = _new_summary(brand, f, t, f_ts, t_ts)
    unqueued = []
    try:
        listing = list_window_headers(client, f_ts, t_ts, budget=budget, t0=t0)
    except OmisellAuthError as e:
        _auth_failure(bis, brand)
        frappe.throw(_("Auth failed: {0}").format(str(e)))
    except OmisellError as e:
        # list-phase failures COUNT toward the circuit breaker (hardening
        # 2026-06-10): a recurring order-list 500 must not retry forever.
        _breaker_record(bis, success=False)
        _ingestion_failure_alert(
            brand,
            "LIST-PHASE failure (client already retried transient 5xx): %s | "
            "window %s..%s | checkpoint held at last_sync_at=%s | "
            "breaker %s/%s" % (e, f, t, bis.last_sync_at,
                               int(bis.consecutive_failures or 0),
                               CIRCUIT_BREAKER_LIMIT),
            context=summary)
        frappe.throw(_("Order list failed: {0}").format(str(e)))
    if listing["timeboxed"]:
        summary["timeboxed"] = listing["timeboxed"]
    headers = listing["headers"]
    summary["listed"] = len(headers)
    summary["listed_order_numbers"] = [h.get("omisell_order_number")
                                       for h in headers[:20]]
    cap = _details_cap()
    if len(headers) > cap:
        summary["capped_at"] = cap
        headers = headers[:cap]
    _process_headers(brand, bis, client, headers, budget, t0, summary, unqueued)
    summary["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    summary["unqueued_failures"] = len(unqueued)
    # CHECKPOINT (Hotfix B): advance when every failed order is durably QUEUED
    # for retry (unqueued == 0) and the window was not capped/timeboxed.
    if len(unqueued) == 0 and not summary.get("capped_at") and not summary.get("timeboxed"):
        bis.reload()
        prev = get_datetime(bis.last_sync_at) if bis.last_sync_at else None
        bis.last_sync_at = prev if (prev and prev > t) else t
        bis.save(ignore_permissions=True)
        summary["last_sync_at_advanced"] = True
        summary["checkpoint_held"] = bool(prev and prev > t)
        _breaker_record(bis, success=True)
    else:
        # only UNQUEUED (auth/persist/system) failures open the breaker; a
        # purely capped/timeboxed chunk holds but does NOT (unchanged).
        if unqueued:
            _ingestion_failure_alert(
                brand, "%d UNQUEUED failures in window %s..%s (queued=%d)" % (
                    len(unqueued), f, t, summary["queued_for_retry"]),
                context=summary)
            _breaker_record(bis, success=False)
        summary["last_sync_at_advanced"] = False
    return summary


@frappe.whitelist(methods=["POST"])
def pull_recent(brand, max_chunks=None):
    """Hotfix 2026-06-09: ENQUEUES the catch-up as a background job (queue
    "long") and returns immediately - heavy paced API work never runs inside
    a web request again. Concurrency: one run per brand (cache lock).
    Follow progress with pull_status(brand)."""
    frappe.only_for("System Manager")
    if _pull_disabled():
        frappe.throw(_("Pulls are disabled (ec_alerts_pull_disabled is set)."))
    bis = _get_bis(brand)
    _breaker_check(bis)
    cache = frappe.cache()
    if cache.get_value(_running_key(brand)):
        frappe.throw(_("A pull for brand {0} is already running. "
                       "Check pull_status.").format(brand))
    cache.set_value(_running_key(brand), now_datetime().isoformat(),
                    expires_in_sec=RUNNING_FLAG_TTL)
    try:
        job = frappe.enqueue(
            "ecentric_workspace.alerts.api_omisell.pull_recent_job",
            queue="long", timeout=JOB_RQ_TIMEOUT, job_name="omisell_pull_%s" % brand,
            brand=brand, max_chunks=int(max_chunks or MAX_CHUNKS_PER_RUN))
    except Exception:
        # Hotfix 2026-06-12: a failed enqueue must not leave the brand locked
        # for RUNNING_FLAG_TTL (the job's own finally never runs in that case).
        cache.delete_value(_running_key(brand))
        raise
    return {"queued": True, "brand": brand,
            "job_id": getattr(job, "id", None),
            "note": "Background job started. Poll "
                    "ecentric_workspace.alerts.api_omisell.pull_status."}


def _overlap_minutes():
    """Scheduled-pull overlap (2026-06-10 hotfix): re-scan effective_from =
    last_sync_at - overlap so the order-list API's late/out-of-order updates
    are not missed. Order Log is upserted + Alert Occurrence deduped, so the
    overlap creates NO duplicate business records. site_config
    ec_alerts_pull_overlap_minutes (default 360); fail-safe to default."""
    try:
        v = frappe.conf.get("ec_alerts_pull_overlap_minutes")
    except Exception:
        return 360
    if v is None or v == "":
        return 360
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return 360


def pull_recent_job(brand, max_chunks=MAX_CHUNKS_PER_RUN):
    """Background worker body (NOT whitelisted, NOT scheduled). Chunk-level
    checkpointing via pull_orders; generous per-chunk timebox; summary stored
    in cache (24h) + as a Comment on the BIS record for audit."""
    cache = frappe.cache()
    run = {"brand": brand, "started_at": str(now_datetime()),
           "chunks_done": 0, "summaries": [], "state": "running"}
    try:
        bis = _get_bis(brand)
        requested_from = (get_datetime(bis.last_sync_at) if bis.last_sync_at
                          else get_datetime(now_datetime()) - timedelta(hours=1))
        overlap = _overlap_minutes()
        end = get_datetime(now_datetime())
        # overlap re-scan: pull from (last_sync_at - overlap). The checkpoint
        # (last_sync_at) still advances ONLY on a fully-successful chunk inside
        # pull_orders - the overlap changes the START, never the checkpoint.
        start = requested_from - timedelta(minutes=overlap)
        if start > end:
            start = end
        # Enough <=1h chunks to span [effective_from, now] so the run REACHES
        # now (forward progress) instead of stopping mid-window and letting the
        # monotonic guard pin the checkpoint. Bounded by MAX_OVERLAP_CHUNKS to
        # cap work (empty windows are ~1 cheap list call each).
        span_chunks = int((end - start).total_seconds() // MAX_WINDOW_SECONDS) + 1
        eff_chunks = min(max(int(max_chunks), span_chunks), MAX_OVERLAP_CHUNKS)
        chunks = chunk_windows(start, end, max_chunks=eff_chunks)
        # TZ-FIX 2026-06-10 diagnostics: the exact epochs the run will send
        # and their UTC read-back, so pull_status proves windows are correct
        # (utc_from should equal site time minus the site-tz offset, -7h).
        run.update({"requested_from": str(requested_from),
                    "effective_from_after_overlap": str(start),
                    "overlap_minutes": overlap,
                    "epoch_from": _to_epoch(start), "epoch_to": _to_epoch(end),
                    "utc_from": utc_str(_to_epoch(start)),
                    "utc_to": utc_str(_to_epoch(end)),
                    "site_time_zone": _site_timezone(),
                    "from": str(start), "to": str(end),
                    "chunks_planned": len(chunks)})
        # Adaptive scalability (2026-06-14): ONE brand-level time budget for the
        # whole run. Each top-level <=1h chunk is handled by the adaptive
        # orchestrator, which splits dense windows (count > cap) into
        # sub-windows within cap and advances the checkpoint at EVERY completed
        # leaf. The orchestrator OWNS the checkpoint; this loop only reads its
        # telemetry and decides whether to start the next chunk.
        _breaker_check(bis)
        client = OmisellClient(bis.name)
        budget = _brand_budget_seconds()
        deadline = time.monotonic() + budget
        tele = {"split_depth": 0, "subwindows_seen": 0, "subwindows_processed": 0,
                "checkpoint_advanced_to": None, "minimum_window_reached": False,
                "budget_exhausted": False, "stop_reason": None,
                "parent_window": None, "leaf_summaries": [],
                "run_window": [str(start), str(end)], "brand_budget_seconds": budget}
        run["telemetry"] = tele
        for cf, ct in chunks:
            if time.monotonic() >= deadline:
                tele["budget_exhausted"] = True
                tele["stop_reason"] = tele["stop_reason"] or swp.BUDGET_EXHAUSTED
                break
            tele["parent_window"] = [str(cf), str(ct)]
            state = pull_window_adaptive(brand, bis, client, cf, ct, deadline, 0, tele)
            if state == swp.COMPLETED:
                run["chunks_done"] += 1
                continue
            break    # any non-completed stop: telemetry holds the explicit reason
        run["summaries"] = tele["leaf_summaries"]
        seen = []
        for s in tele["leaf_summaries"]:
            for n in (s.get("listed_order_numbers") or []):
                if n not in seen:
                    seen.append(n)
        run["listed_order_numbers"] = seen
        run["listed_total"] = sum(int(s.get("listed") or 0) for s in tele["leaf_summaries"])
        # progressive-checkpoint-aware rollup + EXPLICIT stop fields (binding 4):
        # the worker may finish cleanly (state="done") while backlog remains -
        # caught_up=False + stop_reason + checkpoint_advanced_to + remaining_window.
        cp = tele.get("checkpoint_advanced_to")
        cp_dt = get_datetime(cp) if cp else start
        remaining = max(0, int((end - cp_dt).total_seconds()))
        tele["remaining_window_seconds"] = remaining
        tele["remaining_window"] = [str(cp_dt), str(end)]
        run["caught_up"] = (tele["stop_reason"] in (None, swp.COMPLETED)) and remaining == 0
        run["stop_reason"] = (swp.COMPLETED if run["caught_up"]
                              else (tele["stop_reason"] or swp.BUDGET_EXHAUSTED))
        run["checkpoint_advanced_to"] = tele.get("checkpoint_advanced_to")
        run["remaining_window"] = tele["remaining_window"]
        run["remaining_window_seconds"] = remaining
        run["split_depth"] = tele["split_depth"]
        run["subwindows_processed"] = tele["subwindows_processed"]
        run["minimum_window_capped"] = tele["minimum_window_reached"]
        run["budget_exhausted"] = tele["budget_exhausted"]
        run["state"] = "done"
    except Exception as e:
        run["state"] = "error"
        run["error"] = str(e)[:300]
        frappe.log_error(frappe.get_traceback(), "alerts.omisell.pull_recent_job %s" % brand)
    finally:
        cache.delete_value(_running_key(brand))
        run["finished_at"] = str(now_datetime())
        cache.set_value(_last_run_key(brand), json.dumps(run, default=str),
                        expires_in_sec=86400)
        try:
            bis_name = frappe.db.get_value(
                "EC Brand Integration Settings",
                {"brand": brand, "integration_type": "Omisell"}, "name")
            if bis_name:
                frappe.get_doc("EC Brand Integration Settings", bis_name).add_comment(
                    "Comment", "pull_recent_job: %s" % json.dumps(run, default=str)[:1500])
        except Exception:
            pass
    return run


@frappe.whitelist(methods=["POST"])
def pull_status(brand):
    """Read-only: running flag + last run summary + checkpoint state."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand, require_enabled=False)
    cache = frappe.cache()
    last = cache.get_value(_last_run_key(brand))
    if isinstance(last, bytes):
        last = last.decode()
    try:
        raw_flag = frappe.conf.get("ec_alerts_pull_disabled")
    except Exception:
        raw_flag = "<config read error>"
    return {"brand": brand,
            "running_since": cache.get_value(_running_key(brand)),
            "last_sync_at": str(bis.last_sync_at) if bis.last_sync_at else None,
            "consecutive_failures": int(bis.consecutive_failures or 0),
            "pull_disabled": _pull_disabled(),
            "pull_disabled_raw": None if raw_flag is None else str(raw_flag),
            "overlap_minutes": _overlap_minutes(),
            "site_time_zone": _site_timezone(),  # TZ-FIX 2026-06-10
            "last_run": json.loads(last) if last else None}


@frappe.whitelist(methods=["POST"])
def pull_preview(brand, hours=1):
    """Read-only DRY-RUN COUNT: how many orders would the next window list?
    Calls ONLY the order-list endpoint (no details, no DB writes) - cheap and
    safe to run any time before a real pull."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    start = (get_datetime(bis.last_sync_at) if bis.last_sync_at
             else get_datetime(now_datetime()) - timedelta(hours=1))
    end = min(start + timedelta(hours=min(int(hours or 1), 4)),
              get_datetime(now_datetime()))
    # TZ-FIX 2026-06-10: site-tz-aware (was int(start.timestamp()) = server tz)
    s_ts, e_ts = _to_epoch(start), _to_epoch(end)
    payload = client.get_orders(s_ts, e_ts, page=1, page_size=1)
    data = (payload or {}).get("data") or {}
    return {"brand": brand, "window": [str(start), str(end)],
            "epoch_window": [s_ts, e_ts],
            "utc_window": [utc_str(s_ts), utc_str(e_ts)],
            "would_list": data.get("count"),
            "rate_limit_header": client.last_rate_header}


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
