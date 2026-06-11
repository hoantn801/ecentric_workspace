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
from ecentric_workspace.alerts.services import omisell_normalizer as norm
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellAuthError, OmisellClient, OmisellError, sanitize)
from ecentric_workspace.alerts.services.time_windows import epoch_in_tz, utc_str
from ecentric_workspace.alerts.services import pull_planner

MAX_WINDOW_SECONDS = 3600  # hard MVP guard on pull_orders
MAX_LIST_PAGES = 20
# Phase D.1 capacity hardening (approved 2026-06-09):
MAX_DETAILS_PER_RUN = 300        # per-run order-detail cap (config-tunable)
MAX_CHUNKS_PER_RUN = 4           # catch-up chunks (<=1h each) per pull_recent run
MAX_OVERLAP_CHUNKS = 12          # hard cap when the overlap re-scan widens the window
# Catch-up fix 2026-06-12: the per-run work cap is a SPAN (12h - what the old
# "12 chunks x 1h" cap really meant), NOT a chunk count. With adaptive 30m
# chunks a fixed count of 12 covered only 6h = the overlap itself, so a stale
# checkpoint could never reach `now` (LOF-VN incident).
MAX_CATCHUP_SPAN_SECONDS = MAX_OVERLAP_CHUNKS * MAX_WINDOW_SECONDS  # 12h
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

    summary = {"brand": brand, "window": [str(f), str(t)],
               "epoch_window": [f_ts, t_ts],
               "utc_window": [utc_str(f_ts), utc_str(t_ts)], "listed": 0,
               "ingested": 0, "skipped_status": 0, "skipped_status_detail": {},
               "failed": 0, "failed_order_numbers": [], "failed_error_summary": {},
               "listed_order_numbers": [], "skipped_manual": [], "results": []}
    headers, page = [], 1
    try:
        while page <= MAX_LIST_PAGES:
            if time.monotonic() - t0 > budget:
                summary["timeboxed"] = "during_list"
                break
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
        # Hardening 2026-06-10: list-phase failures now COUNT toward the
        # circuit breaker (previously only detail/ingest failures did - a
        # recurring order-list 500 could retry forever without opening it).
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

    summary["listed"] = len(headers)
    summary["listed_order_numbers"] = [h.get("omisell_order_number")
                                       for h in headers[:20]]
    skip_list = _skip_orders()
    cap = _details_cap()
    if len(headers) > cap:
        summary["capped_at"] = cap
        headers = headers[:cap]
    batch = []
    for h in headers:
        if time.monotonic() - t0 > budget:
            summary["timeboxed"] = summary.get("timeboxed") or "during_details"
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
            break
        except OmisellError as e:
            summary["failed"] += 1
            summary["failed_order_numbers"].append(number)
            summary["failed_error_summary"][str(number)] = str(e)[:140]
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
        for r in ing:
            if r.get("status") in ("failed", "check_failed"):
                summary["failed"] += 1
                num = r.get("external_order_id") or r.get("order")
                summary["failed_order_numbers"].append(num)
                summary["failed_error_summary"][str(num)] = "ingest_%s (see Error Log)" % r.get("status")
        summary["action_queue"] = action_queue.process_pending_actions()
    summary["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    if summary["failed"] == 0 and not summary.get("capped_at") and not summary.get("timeboxed"):
        bis.reload()
        # MONOTONIC checkpoint (overlap hotfix 2026-06-10): never move
        # last_sync_at backward. The scheduled pull re-scans
        # [last_sync_at - overlap, now]; an overlap/re-scan chunk that ends in
        # already-checkpointed time must NOT regress the checkpoint.
        prev = get_datetime(bis.last_sync_at) if bis.last_sync_at else None
        bis.last_sync_at = prev if (prev and prev > t) else t
        bis.save(ignore_permissions=True)
        summary["last_sync_at_advanced"] = True
        summary["checkpoint_held"] = bool(prev and prev > t)
        _breaker_record(bis, success=True)
    else:
        if summary["failed"]:
            _ingestion_failure_alert(
                brand, "%d failures in window %s..%s" % (summary["failed"], f, t),
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
        # Resilience 2026-06-11: a failed enqueue must not leave the brand
        # locked for RUNNING_FLAG_TTL (the job's own finally never runs).
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


ADAPTIVE_LISTED_HI = 60      # chunk listing this many orders => halve next run's window
ADAPTIVE_ELAPSED_HI = 240.0  # seconds spent on one chunk => halve next run's window


def _chunk_seconds(brand):
    """Adaptive chunk size (resilience 2026-06-11, LOF read-timeout incident).
    Default 1h. Explicit site_config ec_alerts_pull_chunk_seconds wins
    (clamped 300..3600, no schema change). Otherwise: if the PREVIOUS run had
    a heavy chunk (listed >= 60 or elapsed >= 240s), use 30m chunks this run -
    smaller windows mean fewer detail GETs per chunk, so one timeout costs
    less re-work and the checkpoint advances more often. Fail-safe 1h."""
    try:
        v = frappe.conf.get("ec_alerts_pull_chunk_seconds")
        if v not in (None, ""):
            return max(300, min(int(float(v)), MAX_WINDOW_SECONDS))
    except Exception:
        pass
    try:
        last = frappe.cache().get_value(_last_run_key(brand))
        if isinstance(last, bytes):
            last = last.decode()
        run = json.loads(last) if last else {}
        for s in (run.get("summaries") or []):
            if int(s.get("listed") or 0) >= ADAPTIVE_LISTED_HI or \
                    float(s.get("elapsed_seconds") or 0) >= ADAPTIVE_ELAPSED_HI:
                return 1800
    except Exception:
        pass
    return MAX_WINDOW_SECONDS


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
        cs = _chunk_seconds(brand)
        # Catch-up fix 2026-06-12: span-based planning (pure, tested in
        # services/pull_planner.py). required = ceil(window/cs); cap = 12h
        # of span regardless of chunk size; truncation is REPORTED, never
        # silently dressed up as caught_up.
        p = pull_planner.plan(start, end, cs, int(max_chunks),
                              MAX_CATCHUP_SPAN_SECONDS)
        chunks = p["chunks"]
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
                    "chunk_seconds": cs,
                    "required_chunks": p["required_chunks"],
                    "planned_to": str(p["planned_end"]),
                    "from": str(start), "to": str(end),
                    "chunks_planned": len(chunks)})
        budget_per_chunk = JOB_TIME_BUDGET / max(len(chunks), 1)
        last_end = None  # end of the last fully successful chunk
        for cf, ct in chunks:
            try:
                s = pull_orders(brand, str(cf), str(ct), time_budget=budget_per_chunk)
            except Exception as e:
                # Resilience 2026-06-11: classify + record the failed chunk so
                # pull_status is actionable. Checkpoint of COMPLETED chunks is
                # already saved inside pull_orders - re-raise lets the outer
                # handler set state=error; the finally block clears the lock;
                # the NEXT run resumes from last_sync_at - overlap.
                msg = str(e)
                low = msg.lower()
                run["failed_chunk_window"] = [str(cf), str(ct)]
                run["timeout"] = ("timeout" in low or "timed out" in low)
                run["failed_stage"] = ("list" if "Order list failed" in msg
                                       else "auth" if "Auth" in msg
                                       else "detail" if "Order fetch" in msg
                                       else "other")
                run["stopped"] = ("chunk raised - checkpoint holds at last "
                                  "successful chunk")
                raise
            run["summaries"].append({k: s.get(k) for k in
                                     ("window", "epoch_window", "utc_window",
                                      "listed", "ingested", "skipped_status",
                                      "skipped_status_detail", "skipped_manual",
                                      "failed", "failed_order_numbers",
                                      "failed_error_summary", "listed_order_numbers",
                                      "capped_at", "timeboxed",
                                      "elapsed_seconds", "last_sync_at_advanced")})
            if not s.get("last_sync_at_advanced"):
                run["stopped"] = "chunk incomplete (failed/capped/timeboxed) - checkpoint holds"
                break
            run["chunks_done"] += 1
            last_end = ct  # checkpoint advanced to here (monotonic, inside pull_orders)
        # run-level rollup of what the order-list API actually returned (for
        # pull_status visibility / verifying the overlap caught the order)
        seen = []
        for s in run["summaries"]:
            for n in (s.get("listed_order_numbers") or []):
                if n not in seen:
                    seen.append(n)
        run["listed_order_numbers"] = seen
        run["listed_total"] = sum(int(s.get("listed") or 0) for s in run["summaries"])
        # Catch-up fix 2026-06-12: caught_up ONLY when every planned chunk
        # completed AND the plan actually reaches `to` (the old count-based
        # check reported caught_up=true on a span-truncated plan).
        done_all = run["chunks_done"] == len(chunks)
        run["caught_up"] = bool(done_all and not p["truncated"])
        if not run["caught_up"]:
            nf = last_end or start
            if p["truncated"]:
                run["capped_at"] = len(chunks)
            run["next_from"] = str(nf)
            run["remaining_seconds"] = max(0, int((end - nf).total_seconds()))
        run["state"] = "done" if run["caught_up"] else "done_partial"
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
